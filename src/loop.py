"""Main loop orchestrator for looper."""

import time
from pathlib import Path

from src.log import Logger
from src.parse import (
    detect_asking_input,
    detect_rate_limit,
    detect_session_limit,
    extract_session_id,
    get_display_text,
)
from src.process import build_cmd, run_once
from src.status import run_feedback_agent, write_status

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def loop(
    prompt: str,
    provider: str = "claude",
    timeout: int = 900,
    limit_wait: int = 3600,
    workspace: str | None = None,
):
    """Run provider in a loop until ctrl+c.

    Args:
        prompt: The task to run.
        provider: "claude" or "codex".
        timeout: Seconds before killing a stuck iteration.
        limit_wait: Seconds to sleep when rate/session limited.
        workspace: Directory to run in. Defaults to ./workspace.
    """
    ws = Path(workspace) if workspace else Path.cwd() / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    ws_str = str(ws.resolve())

    logger = Logger(ws_str)
    session_id = None
    iteration = 0
    current_prompt = prompt

    print(f"looper | provider={provider} timeout={timeout}s limit_wait={limit_wait}s")
    print(f"workspace: {ws_str}")
    print(f"log: {logger.path}")
    print("-" * 60)

    try:
        while True:
            iteration += 1

            if iteration > 1 and session_id and provider == "claude":
                cmd = build_cmd(provider, current_prompt, session_id=session_id)
            else:
                cmd = build_cmd(provider, current_prompt)

            print(f"\n>> iteration {iteration}" + (f" (session: {session_id[:20]}...)" if session_id else ""))
            logger.iteration_start(iteration, cmd)

            raw_output, exit_code, elapsed = run_once(cmd, timeout, cwd=ws_str)
            logger.iteration_output(raw_output, exit_code, elapsed)

            # Display tail of readable output
            display_text = get_display_text(provider, raw_output)
            lines = display_text.strip().splitlines()
            tail = lines[-30:] if len(lines) > 30 else lines
            for line in tail:
                print(f"  {line}")

            print(f"\n  exit={exit_code} time={elapsed:.0f}s lines={len(lines)}")

            # --- detection (order matters) ---
            event = "ok"

            # 1. Timeout
            if exit_code == 124:
                event = "timeout"
                print("  ** timed out -- retrying")
                logger.event("timeout -- retrying")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                continue

            # 2. Rate limit
            if detect_rate_limit(raw_output):
                event = "rate_limit"
                print(f"  ** rate limit (rejected) -- waiting {limit_wait}s")
                logger.event(f"rate limit -- waiting {limit_wait}s")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                time.sleep(limit_wait)
                continue

            # 3. Session/usage limit
            if detect_session_limit(raw_output):
                event = "session_limit"
                print(f"  ** session limit hit -- waiting {limit_wait}s")
                logger.event(f"session limit -- waiting {limit_wait}s")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                time.sleep(limit_wait)
                continue

            # 4. Model asking for input
            if detect_asking_input(display_text):
                event = "asked_input"
                print("  ** model asked for input -- retrying")
                logger.event("model asked for input -- retrying")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                continue

            # 5. Non-zero exit code (not timeout, not rate limit)
            if exit_code != 0:
                event = "error"
                print(f"  ** exit code {exit_code} -- retrying")
                logger.event(f"exit code {exit_code} -- retrying")
                write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)
                continue

            # 6. Success — extract session ID for next iteration
            if provider == "claude":
                new_sid = extract_session_id(raw_output)
                if new_sid:
                    session_id = new_sid

            print("  ok")
            logger.event("iteration ok")

            # Write status and run feedback agent
            status_path = write_status(ws_str, iteration, event, exit_code, elapsed, session_id, raw_output)

            print("  running feedback agent...")
            logger.event("running feedback agent")
            feedback = run_feedback_agent(ws_str, status_path)

            if feedback:
                print(f"  feedback: {feedback[:200]}{'...' if len(feedback) > 200 else ''}")
                logger.event(f"feedback: {feedback}")
                # Build next prompt from template
                template = (PROMPTS_DIR / "continue_with_feedback.md").read_text()
                current_prompt = template.replace("{feedback}", feedback).replace("{original_task}", prompt)
            else:
                print("  no feedback (agent failed or timed out)")
                logger.event("no feedback from agent")
                current_prompt = "continue"

    except KeyboardInterrupt:
        print(f"\n\nInterrupted after {iteration} iterations.")
        logger.event(f"interrupted by user after {iteration} iterations")
    finally:
        logger.close()
