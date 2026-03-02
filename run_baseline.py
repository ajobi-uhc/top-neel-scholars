"""Baseline: single Claude CLI session with auto-continue responses.

No RALPH loop, no feedback agent, no progress checkpointing.
Just a single continuous session that auto-responds with
"please continue based on your best judgement" after each turn.
"""

import argparse
from datetime import datetime
from pathlib import Path

from src.log import Logger
from src.parse import detect_asking_input, extract_session_id, get_display_text
from src.process import run_once
from src.rate_monitor import RateMonitor
from src.sandbox import setup_sandbox

AUTO_RESPONSE = "please continue based on your best judgement"


def build_cmd(prompt: str, model: str | None = None,
              resume_session: str | None = None) -> list[str]:
    """Build Claude CLI command — no worker preamble, just the raw prompt."""
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--verbose",
    ]
    if model:
        cmd += ["--model", model]
    if resume_session:
        cmd += ["--resume", resume_session]
    cmd += ["-p", prompt]
    return cmd


def baseline(
    prompt: str,
    model: str | None = None,
    timeout: int = 900,
    max_turns: int = 50,
    max_wait: int = 3600,
    workspace: str | None = None,
    rate_check_interval: float = 60.0,
    rate_threshold: float = 95.0,
):
    """Run a single Claude session, auto-continuing until done or max_turns."""
    ws = Path(workspace) if workspace else Path.cwd() / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    ws_str = str(ws.resolve())

    logger = Logger(ws_str)
    session_id = None
    turn = 0

    # Pretty output file for human reading
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    output_path = log_dir / f"baseline_{stamp}.md"
    output_file = open(output_path, "w")
    output_file.write(f"# Baseline Run — {stamp}\n\n")
    output_file.write(f"**Task:** {prompt.strip()}\n\n")
    output_file.write(f"**Model:** {model or 'default'}\n\n")
    output_file.write(f"**Auto-continue prompt:** \"{AUTO_RESPONSE}\"\n\n")
    output_file.write(f"---\n\n")
    output_file.flush()

    monitor = RateMonitor(
        provider="claude",
        check_interval=rate_check_interval,
        threshold=rate_threshold,
        max_wait=max_wait,
    )
    monitor.start()

    print(f"output: {output_path}")
    print(f"log:    {logger.path}")

    try:
        while turn < max_turns:
            turn += 1
            turn_start = datetime.now()

            monitor.wait_if_needed()

            if turn == 1:
                current_prompt = prompt
            else:
                current_prompt = AUTO_RESPONSE

            cmd = build_cmd(current_prompt, model=model,
                            resume_session=session_id)

            print(f"[{turn_start.strftime('%H:%M:%S')}] turn {turn}/{max_turns} ...", end="", flush=True)
            logger.iteration_start(turn, cmd)

            raw_output, exit_code, elapsed = run_once(
                cmd, timeout, cwd=ws_str, log_file=logger.file,
                cancel_event=monitor.cancel_event, quiet=True,
            )
            logger.iteration_output("", exit_code, elapsed)

            # --- detection ---

            if exit_code == 125:
                print(f" rate-limited ({elapsed:.0f}s)")
                logger.event("cancelled by rate monitor")
                monitor.wait_if_needed()
                turn -= 1
                continue

            if exit_code == 124:
                print(f" timeout ({elapsed:.0f}s)")
                logger.event("timeout -- retrying")
                turn -= 1
                continue

            if exit_code != 0:
                print(f" error exit={exit_code} ({elapsed:.0f}s)")
                logger.event(f"exit code {exit_code} -- retrying")
                turn -= 1
                continue

            # Success — extract session ID for resume
            new_sid = extract_session_id(raw_output)
            if new_sid:
                session_id = new_sid

            display_text = get_display_text("claude", raw_output)

            if detect_asking_input(display_text):
                status = "asked input — auto-responding"
                logger.event("model asked for input -- auto-responding")
            else:
                status = "ok"
                logger.event("turn ok -- auto-continuing")

            print(f" {status} ({elapsed:.0f}s)")

            # Print a short preview of Claude's response
            preview = display_text.strip().replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "..."
            print(f"  >> {preview}")

            # Write pretty output to file
            output_file.write(f"## Turn {turn} — {turn_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [{status}]\n\n")
            output_file.write(display_text.strip() + "\n\n")
            output_file.write("---\n\n")
            output_file.flush()

        print(f"[{datetime.now().strftime('%H:%M:%S')}] done — reached max turns ({max_turns})")
        logger.event(f"reached max turns ({max_turns})")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] stopped after {turn} turns")
        logger.event(f"stopped by user after {turn} turns")
    finally:
        output_file.close()
        monitor.stop()
        logger.close()
        print(f"output: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Baseline: single Claude session with auto-continue"
    )
    parser.add_argument("--model", type=str, default=None,
                        help="Model to use (e.g. claude-haiku-4-5-20251001)")
    parser.add_argument("--timeout", type=int, default=900,
                        help="Timeout per turn in seconds (default: 900)")
    parser.add_argument("--max-turns", type=int, default=50,
                        help="Max auto-continue turns (default: 50)")
    parser.add_argument("--rate-threshold", type=float, default=95.0,
                        help="Pause when usage %% exceeds this (0-100)")
    parser.add_argument("--task", type=str, default=None,
                        help="Override the default task prompt")

    args = parser.parse_args()

    TASK = args.task or """\
Build a small Python CLI tool in src/wordfreq.py that:
1. Reads a text file passed as a CLI argument
2. Counts word frequencies (case-insensitive, strip punctuation)
3. Prints the top 10 most common words with their counts
4. Write tests in tests/test_wordfreq.py and make sure they pass
5. Create a sample input file at data/sample.txt with a few paragraphs of text
6. Run the tool on the sample file and verify it works

This should take multiple iterations — get the core logic working first, then tests, then polish.
"""

    # Fork upstream and clone with push access
    SANDBOX_DIR = setup_sandbox()
    print("-" * 60)

    baseline(
        TASK,
        model=args.model,
        timeout=args.timeout,
        max_turns=args.max_turns,
        rate_threshold=args.rate_threshold,
        workspace=str(SANDBOX_DIR),
    )

