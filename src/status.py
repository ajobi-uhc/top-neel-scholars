"""Status tracking and feedback agent.

Writes timestamped status files after each iteration and
spawns a Claude Code subprocess as the feedback agent.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

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
    """Find the most recent checkpoints/<prefix>_*.md file."""
    cp_dir = Path(workspace) / "checkpoints"
    if not cp_dir.exists():
        return None
    md_files = sorted(cp_dir.glob(f"{prefix}_*.md"), reverse=True)
    return md_files[0] if md_files else None


def read_all_feedback(workspace: str) -> str:
    """Read all checkpoints/feedback_*.md files chronologically, return concatenated text."""
    cp_dir = Path(workspace) / "checkpoints"
    if not cp_dir.exists():
        return ""
    files = sorted(cp_dir.glob("feedback_*.md"))
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"--- {f.name} ---\n{f.read_text().strip()}")
    return "\n\n".join(parts)


def run_feedback_agent_cc(
    workspace: str,
    original_task: str,
    progress_content: str,
    feedback_history: str,
    timeout: int = 120,
) -> Path | None:
    """Spawn a Claude Code subprocess as the feedback agent.

    Context is injected directly into the prompt — the agent doesn't read files.
    Returns the path to the feedback file, or None on failure.
    """
    template = (PROMPTS_DIR / "feedback_agent_preamble.md").read_text()
    prompt = (template
        .replace("{original_task}", original_task)
        .replace("{progress_content}", progress_content)
        .replace("{feedback_history}", feedback_history))

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "-p", prompt,
    ]

    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=workspace,
            start_new_session=True,
        )

        # Stream output live
        for line in proc.stdout:
            sys.stdout.write(f"  [feedback] {line}")
            sys.stdout.flush()

        proc.wait(timeout=max(1, timeout - int(time.time() - start)))

        if proc.returncode != 0:
            print(f"  feedback agent exited with code {proc.returncode}")
            return None

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print("  feedback agent timed out")
        return None
    except KeyboardInterrupt:
        proc.kill()
        proc.wait()
        raise

    return find_latest_checkpoint(workspace, "feedback")
