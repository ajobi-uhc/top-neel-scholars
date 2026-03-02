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


def _truncate(text: str, max_lines: int = 40) -> str:
    """Truncate text to max_lines, adding a note if truncated."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def raw_output_to_markdown(raw_output: str) -> str:
    """Convert Claude CLI JSON output to human-readable markdown.

    Parses the verbose JSON stream and formats thinking, tool calls,
    tool results, and text responses into readable markdown.
    """
    try:
        events = json.loads(raw_output)
    except json.JSONDecodeError:
        return raw_output
    if not isinstance(events, list):
        events = [events]

    parts = []
    step = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        etype = event.get("type")

        if etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                btype = block.get("type")

                if btype == "thinking":
                    thinking = block.get("thinking", "").strip()
                    if thinking:
                        step += 1
                        parts.append(f"**Step {step} — Thinking**\n")
                        parts.append(f"> {thinking}\n")

                elif btype == "tool_use":
                    step += 1
                    name = block.get("name", "unknown")
                    inp = block.get("input", {})
                    parts.append(f"**Step {step} — Tool: `{name}`**\n")
                    # Format input based on tool type
                    if name in ("Bash",):
                        cmd = inp.get("command", "")
                        parts.append(f"```bash\n{cmd}\n```\n")
                    elif name in ("Read",):
                        parts.append(f"Reading `{inp.get('file_path', '')}`\n")
                    elif name in ("Write",):
                        fp = inp.get("file_path", "")
                        content = inp.get("content", "")
                        parts.append(f"Writing `{fp}`\n")
                        parts.append(f"```\n{_truncate(content)}\n```\n")
                    elif name in ("Edit",):
                        fp = inp.get("file_path", "")
                        parts.append(f"Editing `{fp}`\n")
                        old = inp.get("old_string", "")
                        new = inp.get("new_string", "")
                        if old or new:
                            parts.append(f"```diff\n- {_truncate(old, 10)}\n+ {_truncate(new, 10)}\n```\n")
                    elif name in ("Glob",):
                        parts.append(f"Pattern: `{inp.get('pattern', '')}`\n")
                    elif name in ("Grep",):
                        parts.append(f"Pattern: `{inp.get('pattern', '')}` in `{inp.get('path', '.')}`\n")
                    else:
                        # Generic: show input as compact JSON
                        compact = json.dumps(inp, indent=2)
                        if len(compact) > 500:
                            compact = compact[:500] + "\n..."
                        parts.append(f"```json\n{compact}\n```\n")

                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        step += 1
                        parts.append(f"**Step {step} — Response**\n")
                        parts.append(f"{text}\n")

        elif etype == "user":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    is_error = block.get("is_error", False)
                    content = block.get("content", "")
                    # Also check tool_use_result for structured output
                    tool_result = event.get("tool_use_result")
                    if isinstance(tool_result, dict):
                        stdout = tool_result.get("stdout", "")
                        stderr = tool_result.get("stderr", "")
                        content = stdout or content
                        if stderr:
                            content += f"\nstderr: {stderr}"
                    elif isinstance(tool_result, str) and tool_result:
                        content = tool_result
                    label = "Error" if is_error else "Result"
                    if content:
                        parts.append(f"*{label}:*\n```\n{_truncate(str(content))}\n```\n")

        elif etype == "result":
            cost = event.get("total_cost_usd")
            num_turns = event.get("num_turns")
            duration = event.get("duration_ms")
            if cost or num_turns or duration:
                summary = []
                if num_turns:
                    summary.append(f"{num_turns} turns")
                if duration:
                    summary.append(f"{duration / 1000:.0f}s")
                if cost:
                    summary.append(f"${cost:.4f}")
                parts.append(f"*Session: {' | '.join(summary)}*\n")

    return "\n".join(parts) if parts else raw_output
