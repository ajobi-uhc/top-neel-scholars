"""Main loop orchestrator."""

from datetime import datetime
from pathlib import Path

from src.log import Logger
from src.parse import (
    detect_asking_input,
    extract_codex_session_id,
    extract_session_id,
    get_display_text,
)
from src.process import build_cmd, run_once
from src.rate_monitor import RateMonitor
from src.status import find_latest_checkpoint, read_all_feedback, run_feedback_agent_cc, write_status

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def loop(
    prompt: str,
    provider: str = "claude",
    model: str | None = None,
    max_wait: int = 3600,
    workspace: str | None = None,
    rate_check_interval: float = 60.0,
    rate_threshold: float = 95.0,
):
    """Run provider in a loop until ctrl+c."""
    ws = Path(workspace) if workspace else Path.cwd() / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    ws_str = str(ws.resolve())

    logger = Logger(ws_str)
    session_id = None
    iteration = 0

    # Pretty markdown output file for human reading
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    output_path = log_dir / f"ralph_{stamp}.md"
    output_file = open(output_path, "w")
    output_file.write(f"# RALPH Run — {stamp}\n\n")
    output_file.write(f"**Task:** {prompt.strip()}\n\n")
    output_file.write(f"**Provider:** {provider} | **Model:** {model or 'default'}\n\n")
    output_file.write(f"---\n\n")
    output_file.flush()

    monitor = RateMonitor(
        provider=provider,
        check_interval=rate_check_interval,
        threshold=rate_threshold,
        max_wait=max_wait,
    )
    monitor.start()

    print(f"provider={provider} max_wait={max_wait}s")
    print(f"workspace: {ws_str}")
    print(f"output: {output_path}")
    print(f"log:    {logger.path}")
    print("-" * 60)

    try:
        while True:
            iteration += 1

            monitor.wait_if_needed()

            # Build prompt: first iteration uses original task, subsequent use template
            if iteration == 1:
                current_prompt = prompt
            else:
                progress_path = find_latest_checkpoint(ws_str, "progress")
                feedback_path = find_latest_checkpoint(ws_str, "feedback")
                if progress_path and feedback_path:
                    progress_content = progress_path.read_text()
                    feedback_content = feedback_path.read_text()
                    template = (PROMPTS_DIR / "continue_with_feedback.md").read_text()
                    current_prompt = (template
                        .replace("{progress_content}", progress_content)
                        .replace("{feedback_content}", feedback_content)
                        .replace("{original_task}", prompt))
                else:
                    current_prompt = prompt

            cmd = build_cmd(provider, current_prompt, model=model)

            iter_start = datetime.now()
            print(f"[{iter_start.strftime('%H:%M:%S')}] iteration {iteration} ...", end="", flush=True)
            logger.iteration_start(iteration, cmd)

            raw_output, exit_code, elapsed = run_once(cmd, cwd=ws_str, log_file=logger.file,
                                                        cancel_event=monitor.cancel_event, quiet=True)
            logger.iteration_output("", exit_code, elapsed)  # output already streamed to log

            # --- detection (order matters) ---
            event = "ok"

            if exit_code == 125:
                event = "rate_cancelled"
                print(f" rate-limited ({elapsed:.0f}s)")
                logger.event("cancelled by rate monitor")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                output_file.write(f"## Iteration {iteration} — {iter_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [rate-limited]\n\n---\n\n")
                output_file.flush()
                monitor.wait_if_needed()
                continue

            if exit_code == 124:
                event = "timeout"
                print(f" timeout ({elapsed:.0f}s)")
                logger.event("timeout -- retrying")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                output_file.write(f"## Iteration {iteration} — {iter_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [timeout]\n\n---\n\n")
                output_file.flush()
                continue

            display_text = get_display_text(provider, raw_output)
            if detect_asking_input(display_text):
                event = "asked_input"
                print(f" asked input ({elapsed:.0f}s)")
                logger.event("model asked for input -- retrying")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                output_file.write(f"## Iteration {iteration} — {iter_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [asked input]\n\n---\n\n")
                output_file.flush()
                continue

            if exit_code != 0:
                event = "error"
                print(f" error exit={exit_code} ({elapsed:.0f}s)")
                logger.event(f"exit code {exit_code} -- retrying")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                output_file.write(f"## Iteration {iteration} — {iter_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [error exit={exit_code}]\n\n---\n\n")
                output_file.flush()
                continue

            # Success — extract session ID for logging
            if provider == "claude":
                new_sid = extract_session_id(raw_output)
                if new_sid:
                    session_id = new_sid
            elif provider == "codex":
                new_sid = extract_codex_session_id()
                if new_sid:
                    session_id = new_sid

            print(f" ok ({elapsed:.0f}s)")
            logger.event("iteration ok")

            # Print a short preview of Claude's response
            preview = display_text.strip().replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "..."
            print(f"  >> {preview}")

            write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)

            # Write worker output to markdown
            output_file.write(f"## Iteration {iteration} — {iter_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [ok]\n\n")
            output_file.write("### Worker Output\n\n")
            output_file.write(display_text.strip() + "\n\n")

            # Find the progress file the worker just wrote
            progress_path = find_latest_checkpoint(ws_str, "progress")
            if progress_path:
                print(f"  progress: {progress_path.name}")
                progress_content = progress_path.read_text()
            else:
                print("  warning: no progress file found")
                progress_content = ""

            # Gather feedback history and run feedback agent
            feedback_history = read_all_feedback(ws_str)

            print("  running feedback agent ...", end="", flush=True)
            logger.event("running feedback agent (Claude Code)")
            feedback_path = run_feedback_agent_cc(
                ws_str,
                original_task=prompt,
                progress_content=progress_content,
                feedback_history=feedback_history,
            )

            if feedback_path:
                feedback_text = feedback_path.read_text()
                print(f" done ({feedback_path.name})")
                logger.event(f"feedback written to: {feedback_path}")
                output_file.write("### Feedback\n\n")
                output_file.write(feedback_text.strip() + "\n\n")
            else:
                print(" no feedback produced")
                logger.event("no feedback file from agent")

            output_file.write("---\n\n")
            output_file.flush()

    except KeyboardInterrupt:
        print(f"\n\nStopped after {iteration} iterations.")
        logger.event(f"stopped by user after {iteration} iterations")
    finally:
        output_file.close()
        monitor.stop()
        logger.close()
        print(f"output: {output_path}")
