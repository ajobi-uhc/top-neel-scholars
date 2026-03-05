"""Status tracking and feedback agent.

Writes timestamped status files after each iteration and
manages a persistent Claude Code subprocess as the feedback agent.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from src.parse import extract_result_text, extract_session_id

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def write_status(
    workspace: str,
    iteration: int,
    event: str,
    exit_code: int,
    elapsed: float,
    session_id: str | None,
    output: str,
) -> Path:
    """Write a timestamped status JSON file for this iteration."""
    status_dir = Path(workspace) / "status"
    status_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sid_part = f"_{session_id[:12]}" if session_id else ""
    path = status_dir / f"status_{stamp}_iter{iteration}{sid_part}.json"

    tail = "\n".join(output.splitlines()[-200:])

    data = {
        "timestamp": datetime.now().isoformat(),
        "iteration": iteration,
        "event": event,
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed, 1),
        "session_id": session_id,
        "output_tail": tail,
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def find_latest_checkpoint(workspace: str, prefix: str) -> Path | None:
    """Find the most recent memories/<prefix>_*.md file."""
    mem_dir = Path(workspace) / "memories"
    if not mem_dir.exists():
        return None
    md_files = sorted(mem_dir.glob(f"{prefix}_*.md"), reverse=True)
    return md_files[0] if md_files else None


def read_all_feedback(workspace: str) -> str:
    """Read all memories/feedback_*.md files chronologically, return concatenated text."""
    mem_dir = Path(workspace) / "memories"
    if not mem_dir.exists():
        return ""
    files = sorted(mem_dir.glob("feedback_*.md"))
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"--- {f.name} ---\n{f.read_text().strip()}")
    return "\n\n".join(parts)


def _run_claude_cmd(cmd: list[str], workspace: str, timeout: int,
                    prefix: str = "[feedback]") -> tuple[str, int]:
    """Run a claude CLI command, stream output, return (raw_output, exit_code)."""
    start = time.time()
    output_lines = []

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=workspace,
        start_new_session=True,
    )

    def _reader():
        for line in proc.stdout:
            sys.stdout.write(f"  {prefix} {line}")
            sys.stdout.flush()
            output_lines.append(line)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    try:
        deadline = start + timeout
        while reader.is_alive():
            remaining = deadline - time.time()
            if remaining <= 0:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait()
                reader.join(timeout=5)
                return "".join(output_lines), 124
            reader.join(timeout=min(0.5, remaining))

        proc.wait(timeout=10)
        return "".join(output_lines), proc.returncode

    except KeyboardInterrupt:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        proc.wait()
        raise


def init_feedback_agent(workspace: str, timeout: int = 300) -> str | None:
    """Initialize the persistent feedback agent session.

    Runs the init prompt and returns the session ID for future --resume calls.
    Returns None on failure.
    """
    init_prompt = (PROMPTS_DIR / "feedback" / "feedback_init.md").read_text()

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "-p", init_prompt,
    ]

    raw_output, exit_code = _run_claude_cmd(cmd, workspace, timeout)

    if exit_code != 0:
        print(f"  feedback agent init failed (exit={exit_code})")
        return None

    session_id = extract_session_id(raw_output)
    return session_id


def run_feedback_agent_cc(
    workspace: str,
    finished_path: Path | None,
    feedback_session_id: str | None,
    timeout: int = 600,
) -> tuple[Path | None, str | None]:
    """Send a feedback prompt to the persistent feedback agent.

    If feedback_session_id is provided, resumes that session.
    Otherwise falls back to a one-shot run.
    Returns (feedback_file_path, session_id).
    """
    if not finished_path:
        return None, feedback_session_id

    timestamp = finished_path.stem.replace("finished_", "")
    template = (PROMPTS_DIR / "feedback" / "feedback_continue.md").read_text()
    prompt = template.replace("{timestamp}", timestamp)

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "json",
    ]
    if feedback_session_id:
        cmd += ["--resume", feedback_session_id]
    cmd += ["-p", prompt]

    start_t = time.time()
    raw_output, exit_code = _run_claude_cmd(cmd, workspace, timeout)
    elapsed = time.time() - start_t

    if exit_code == 124:
        print(f"  feedback agent timed out after {elapsed:.0f}s (limit={timeout}s)")
        return None, feedback_session_id

    if exit_code != 0:
        print(f"  feedback agent exited with code {exit_code} after {elapsed:.0f}s")
        # Dump first 500 chars for debugging
        if raw_output:
            print(f"  [debug] output preview: {raw_output[:500]}")
        return None, feedback_session_id

    print(f" completed in {elapsed:.0f}s (exit=0, output={len(raw_output)} bytes)")

    # Update session ID from output (in case it changed)
    new_sid = extract_session_id(raw_output)
    if new_sid:
        feedback_session_id = new_sid

    # Write feedback file from the agent's output directly,
    # rather than relying on the agent to write it via tool use.
    feedback_text = extract_result_text(raw_output).strip()
    if not feedback_text:
        print(f"  [debug] extract_result_text returned empty. raw_output[:300]: {raw_output[:300]}")
        return find_latest_checkpoint(workspace, "feedback"), feedback_session_id

    mem_dir = Path(workspace) / "memories"
    mem_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = mem_dir / f"feedback_{timestamp}.md"
    feedback_path.write_text(feedback_text)
    return feedback_path, feedback_session_id
