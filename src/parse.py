"""Detection and extraction functions for output parsing.

Pure functions, no side effects.
"""

import glob
import json
import os
import re
from pathlib import Path

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


def extract_codex_response(output: str) -> str:
    """Extract the model's response text from codex exec output.

    Codex stderr contains session metadata. The model response appears
    after the last line that is exactly 'codex', up to 'tokens used'.
    """
    lines = output.strip().splitlines()
    codex_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "codex":
            codex_idx = i
    if codex_idx is None:
        return output
    response = []
    for line in lines[codex_idx + 1:]:
        if line.strip() == "tokens used":
            break
        response.append(line)
    return "\n".join(response)


def extract_session_id(output: str) -> str | None:
    """Extract session ID from Claude CLI JSON output for --resume."""
    try:
        obj = json.loads(output)
        if isinstance(obj, dict):
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


def extract_codex_session_id() -> str | None:
    """Extract session ID from the most recent Codex session JSONL file."""
    sessions_dir = str(Path.home() / ".codex" / "sessions")
    pattern = os.path.join(sessions_dir, "**", "rollout-*.jsonl")
    files = glob.glob(pattern, recursive=True)
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    try:
        with open(latest) as f:
            first_line = f.readline().strip()
            if first_line:
                obj = json.loads(first_line)
                if obj.get("type") == "session_meta":
                    return obj.get("payload", {}).get("id")
    except (json.JSONDecodeError, OSError):
        pass
    return None


def get_display_text(provider: str, raw_output: str) -> str:
    """Get human-readable display text from raw provider output."""
    if provider == "claude":
        return extract_result_text(raw_output)
    elif provider == "codex":
        return extract_codex_response(raw_output)
    return raw_output
