"""
looper — run Claude Code or Codex in a loop with stuck/limit detection.

Usage:
    from looper import loop

    loop("do the thing")
    loop("do the thing", provider="codex")
    loop("do the thing", timeout=600, max_loops=10)
"""

import json
import os
import subprocess
import time
import re
from pathlib import Path

# Text fallback patterns for session/usage limits
SESSION_LIMIT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"usage limit",
        r"5.hour.*limit",
        r"limit.*reached.*try.*back",
        r"usage.*limit.*reached",
        r"quota exceeded",
    ]
]

# Patterns that suggest Claude is asking for user input
# In -p mode Claude won't hang, it just prints the question and exits
INPUT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"would you like",
        r"shall I",
        r"do you want",
        r"please confirm",
        r"waiting for .* input",
    ]
]


def build_cmd(provider: str, prompt: str, session_id: str | None = None) -> list[str]:
    preamble = (
        "IMPORTANT: Never ask for user input or clarification. "
        "Make your best judgment on any decision and proceed. "
        "If you finish, output DONE on its own line.\n\n"
    )
    full_prompt = preamble + prompt

    if provider == "claude":
        cmd = ["claude", "--dangerously-skip-permissions", "--output-format", "json"]
        # --resume with explicit session ID so we don't hijack other claude sessions
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", full_prompt]
        return cmd
    elif provider == "codex":
        return ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", full_prompt]
    else:
        raise ValueError(f"Unknown provider: {provider}")


def detect_rate_limit(output: str) -> bool:
    """Check for rate_limit_event with status 'rejected' in Claude CLI JSON output.
    This is the real structured signal — not a heuristic."""
    for line in output.splitlines():
        if '"rate_limit_event"' in line:
            try:
                obj = json.loads(line)
                event = obj.get("rate_limit_event", {})
                if event.get("status") == "rejected":
                    return True
            except json.JSONDecodeError:
                # Fallback: just check if rejected appears near rate_limit_event
                if "rejected" in line:
                    return True
    return False


def detect_session_limit(output: str) -> bool:
    """Check for 5-hour usage cap / session limits via text patterns.
    Only checks last 30 lines, excluding tool result echoes."""
    tail = "\n".join(output.splitlines()[-30:])
    # Filter out lines that are just tool result JSON
    filtered = "\n".join(
        line for line in tail.splitlines()
        if '"tool_result"' not in line and '"tool_use_id"' not in line
    )
    return any(p.search(filtered) for p in SESSION_LIMIT_PATTERNS)


def detect_asking_input(output: str) -> bool:
    """Check if Claude is asking for user input instead of just doing the task."""
    return any(p.search(output) for p in INPUT_PATTERNS)


def extract_result_text(output: str) -> str:
    """Try to extract the .result field from Claude CLI JSON output."""
    try:
        obj = json.loads(output)
        if isinstance(obj, dict):
            return obj.get("result", output)
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item.get("type") == "result":
                    return item.get("result", output)
    except json.JSONDecodeError:
        pass
    return output


def extract_session_id(output: str) -> str | None:
    """Extract session ID from Claude CLI JSON output for --resume."""
    try:
        obj = json.loads(output)
        if isinstance(obj, dict):
            # Try metadata.session_id first, then top-level session_id, then sessionId
            sid = (obj.get("metadata", {}) or {}).get("session_id")
            if not sid:
                sid = obj.get("session_id") or obj.get("sessionId")
            return sid if sid else None
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item.get("type") == "result":
                    sid = item.get("session_id") or item.get("sessionId")
                    if sid:
                        return sid
    except json.JSONDecodeError:
        pass
    return None


def run_once(cmd: list[str], timeout: int, cwd: str | None = None) -> tuple[str, int]:
    """Run a single iteration. Returns (output, exit_code).
    exit_code 124 = timed out."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        output = ""
        if e.stdout:
            output += e.stdout if isinstance(e.stdout, str) else e.stdout.decode(errors="replace")
        if e.stderr:
            output += e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors="replace")
        return output, 124


def loop(
    prompt: str,
    provider: str = "claude",
    timeout: int = 900,
    limit_wait: int = 3600,
    max_loops: int = 0,
    workspace: str | None = None,
):
    """Run provider in a loop until done or stopped.

    Args:
        prompt: The task to run.
        provider: "claude" or "codex".
        timeout: Seconds before killing a stuck iteration.
        limit_wait: Seconds to sleep when rate/session limited.
        max_loops: Stop after N iterations. 0 = unlimited.
        workspace: Directory to run in. Created if it doesn't exist.
                   Defaults to ./workspace.
    """
    ws = Path(workspace) if workspace else Path.cwd() / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    ws = str(ws.resolve())

    session_id = None  # Will be populated after first successful run
    iteration = 0
    no_change_count = 0
    last_output_hash = None

    print(f"looper | provider={provider} timeout={timeout}s limit_wait={limit_wait}s max={max_loops or '∞'}")
    print(f"workspace: {ws}")
    print("─" * 60)

    while True:
        iteration += 1
        if max_loops and iteration > max_loops:
            print(f"\nHit max loops ({max_loops}). Stopping.")
            break

        cmd = build_cmd(provider, prompt, session_id=session_id)

        print(f"\n▶ iteration {iteration}" + (f" (session: {session_id[:20]}...)" if session_id else ""))
        start = time.time()
        raw_output, exit_code = run_once(cmd, timeout, cwd=ws)
        elapsed = time.time() - start

        # For display, try to show the readable result text
        display_text = extract_result_text(raw_output) if provider == "claude" else raw_output
        lines = display_text.strip().splitlines()
        tail = lines[-30:] if len(lines) > 30 else lines
        for line in tail:
            print(f"  {line}")

        print(f"\n  exit={exit_code} time={elapsed:.0f}s lines={len(lines)}")

        # --- detection (order matters) ---

        # 1. Timeout — process took too long
        if exit_code == 124:
            print("  ⚠ timed out — retrying")
            continue

        # 2. Rate limit — structured JSON signal from Claude CLI
        if detect_rate_limit(raw_output):
            print(f"  ⚠ rate limit (rejected) — waiting {limit_wait}s")
            time.sleep(limit_wait)
            continue

        # 3. Session/usage limit — 5-hour cap etc
        if detect_session_limit(raw_output):
            print(f"  ⚠ session limit hit — waiting {limit_wait}s")
            time.sleep(limit_wait)
            continue

        # 4. Model asking for input — retry with same prompt (preamble tells it not to ask)
        if detect_asking_input(display_text):
            print("  ⚠ model asked for input — retrying")
            continue

        # 5. Circuit breaker — identical output 3x
        output_hash = hash(raw_output.strip())
        if output_hash == last_output_hash:
            no_change_count += 1
        else:
            no_change_count = 0
        last_output_hash = output_hash

        if no_change_count >= 3:
            print("  ⚠ output unchanged for 3 iterations — stopping")
            break

        # 6. Model said it's done
        if any("DONE" == l.strip() for l in lines[-5:]):
            print("\n✓ model signaled DONE")
            break

        # 7. Non-zero exit code (not timeout, not rate limit) — retry
        if exit_code != 0:
            print(f"  ⚠ exit code {exit_code} — retrying")
            continue

        # Extract session ID for --resume on next iteration
        if provider == "claude":
            new_sid = extract_session_id(raw_output)
            if new_sid:
                session_id = new_sid

        print("  ✓ ok")
