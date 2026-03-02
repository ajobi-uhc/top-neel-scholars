"""Baseline: single CLI session with auto-continue responses.

No RALPH loop, no feedback agent, no progress checkpointing.
Just a single continuous session that auto-responds with
"please continue based on your best judgement" after each turn.

Supports both Claude Code and Codex CLI providers.
"""

import argparse
from datetime import datetime
from pathlib import Path

from src.log import Logger
from src.parse import (
    codex_output_to_markdown,
    detect_asking_input,
    extract_codex_session_id,
    extract_session_id,
    get_display_text,
    raw_output_to_markdown,
)
from src.process import run_once
from src.rate_monitor import RateMonitor
from src.sandbox import setup_sandbox
from src.status import write_status

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def build_cmd(provider: str, prompt: str, model: str | None = None,
              resume_session: str | None = None) -> list[str]:
    """Build CLI command — no worker preamble, just the raw prompt."""
    if provider == "codex":
        cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--json"]
        if model:
            cmd += ["-m", model]
        if resume_session:
            cmd += ["resume", resume_session, prompt]
        else:
            cmd += [prompt]
        return cmd

    # claude (default)
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
    provider: str = "claude",
    model: str | None = None,
    timeout: int = 900,
    max_turns: int | None = None,
    max_wait: int = 3600,
    workspace: str | None = None,
    rate_check_interval: float = 60.0,
    rate_threshold: float = 95.0,
):
    """Run a single CLI session, auto-continuing until done or max_turns (if set)."""
    ws = Path(workspace) if workspace else Path.cwd() / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    ws_str = str(ws.resolve())

    logger = Logger(ws_str)
    session_id = None
    turn = 0

    # Per-run directory for human-readable markdown logs
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = Path(__file__).resolve().parent / "logs" / f"baseline_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    monitor = RateMonitor(
        provider=provider,
        check_interval=rate_check_interval,
        threshold=rate_threshold,
        max_wait=max_wait,
    )
    monitor.start()

    print(f"output: {run_dir}")
    print(f"log:    {logger.path}")

    turns_label = str(max_turns) if max_turns else "∞"

    try:
        while max_turns is None or turn < max_turns:
            turn += 1
            turn_start = datetime.now()

            monitor.wait_if_needed()

            if turn == 1:
                current_prompt = (PROMPTS_DIR / "baseline" / "start.md").read_text()
            else:
                current_prompt = (PROMPTS_DIR / "baseline" / "continuation.md").read_text()

            cmd = build_cmd(provider, current_prompt, model=model,
                            resume_session=session_id)

            print(f"[{turn_start.strftime('%H:%M:%S')}] turn {turn}/{turns_label} ...", end="", flush=True)
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
                write_status(ws_str, turn, "rate_cancelled", exit_code, elapsed, session_id, raw_output)
                monitor.wait_if_needed()
                turn -= 1
                continue

            if exit_code == 124:
                print(f" timeout ({elapsed:.0f}s)")
                logger.event("timeout -- retrying")
                write_status(ws_str, turn, "timeout", exit_code, elapsed, session_id, raw_output)
                turn -= 1
                continue

            if exit_code != 0:
                print(f" error exit={exit_code} ({elapsed:.0f}s)")
                logger.event(f"exit code {exit_code} -- retrying")
                write_status(ws_str, turn, "error", exit_code, elapsed, session_id, raw_output)
                turn -= 1
                continue

            # Success — extract session ID for resume
            if provider == "codex":
                new_sid = extract_codex_session_id()
            else:
                new_sid = extract_session_id(raw_output)
            if new_sid:
                session_id = new_sid

            display_text = get_display_text(provider, raw_output)

            if detect_asking_input(display_text):
                event = "asked_input"
                status = "asked input — auto-responding"
                logger.event("model asked for input -- auto-responding")
            else:
                event = "ok"
                status = "ok"
                logger.event("turn ok -- auto-continuing")

            print(f" {status} ({elapsed:.0f}s)")
            write_status(ws_str, turn, event, exit_code, elapsed, session_id, raw_output)

            # Print a short preview of Claude's response
            preview = display_text.strip().replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "..."
            print(f"  >> {preview}")

            # Write per-turn markdown file
            if provider == "codex":
                detailed_md = codex_output_to_markdown(raw_output)
            else:
                detailed_md = raw_output_to_markdown(raw_output)
            turn_path = run_dir / f"turn_{turn:02d}.md"
            turn_path.write_text(
                f"# Turn {turn} — {turn_start.strftime('%H:%M:%S')} ({elapsed:.0f}s) [{status}]\n\n"
                + detailed_md.strip() + "\n"
            )

        print(f"[{datetime.now().strftime('%H:%M:%S')}] done — reached max turns ({max_turns})")
        logger.event(f"reached max turns ({max_turns})")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] stopped after {turn} turns")
        logger.event(f"stopped by user after {turn} turns")
    finally:
        monitor.stop()
        logger.close()
        print(f"output: {run_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Baseline: single CLI session with auto-continue"
    )
    parser.add_argument("--provider", choices=["claude", "codex"], default="claude",
                        help="Which CLI to use (default: claude)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model to use (e.g. claude-haiku-4-5-20251001)")
    parser.add_argument("--timeout", type=int, default=900,
                        help="Timeout per turn in seconds (default: 900)")
    parser.add_argument("--max-turns", type=int, default=None,
                        help="Max auto-continue turns (default: unlimited)")
    parser.add_argument("--rate-threshold", type=float, default=95.0,
                        help="Pause when usage %% exceeds this (0-100)")

    args = parser.parse_args()

    SANDBOX_DIR = setup_sandbox(provider=args.provider, mode="baseline")
    print("-" * 60)

    baseline(
        provider=args.provider,
        model=args.model,
        timeout=args.timeout,
        max_turns=args.max_turns,
        rate_threshold=args.rate_threshold,
        workspace=str(SANDBOX_DIR),
    )
