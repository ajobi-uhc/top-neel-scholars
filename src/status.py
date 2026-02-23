"""Status tracking and feedback agent for looper.

Writes timestamped status files after each iteration and
calls the OpenRouter API for feedback.
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

OPENROUTER_MODEL = "anthropic/claude-sonnet-4"
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENROUTER_API_KEY not found in env or .env file")


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


def _find_latest_status_md(workspace: str) -> Path | None:
    """Find the most recent status_*.md file written by the worker agent."""
    status_dir = Path(workspace) / "status"
    if not status_dir.exists():
        return None
    md_files = sorted(status_dir.glob("status_*.md"), reverse=True)
    return md_files[0] if md_files else None


def run_feedback_agent(workspace: str, status_path: Path, timeout: int = 60) -> str | None:
    """Call OpenRouter API to review the worker's status markdown.

    Looks for the latest status_*.md written by the worker agent.
    Falls back to the JSON status file if none exist.
    Returns feedback text or None on failure.
    """
    try:
        api_key = _load_api_key()
    except Exception:
        return None

    latest_md = _find_latest_status_md(workspace)
    if latest_md:
        status_content = latest_md.read_text()
    else:
        status_content = status_path.read_text()

    prompt_template = (PROMPTS_DIR / "feedback.md").read_text()
    prompt = prompt_template.replace("{status_content}", status_content)

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except KeyboardInterrupt:
        raise
    except Exception:
        return None
