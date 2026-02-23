#!/usr/bin/env python3
"""Filter raw looper log into readable output. Reads stdin line-by-line.

The Claude CLI with --output-format json emits one huge JSON array per
iteration containing every message. We extract just the useful bits:
  - assistant text blocks
  - tool use names
  - the final result + cost summary
"""

import json
import sys


def parse_json_blob(line: str) -> str | None:
    """Parse a Claude CLI JSON array/object and return readable summary."""
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None

    if isinstance(obj, dict):
        obj = [obj]
    if not isinstance(obj, list):
        return None

    parts = []
    for item in obj:
        if not isinstance(item, dict):
            continue

        typ = item.get("type", "")

        # Skip system init (huge, not useful)
        if typ == "system":
            subtype = item.get("subtype", "")
            if subtype == "init":
                sid = item.get("session_id", "?")
                parts.append(f"\033[0;37m  [session: {sid[:30]}]\033[0m")
            continue

        # Assistant messages: show text and tool names
        if typ == "assistant":
            message = item.get("message", {})
            for block in message.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        parts.append(text)
                elif block.get("type") == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    # Show a short summary of what the tool is doing
                    detail = ""
                    if name in ("Read", "Glob", "Grep"):
                        detail = inp.get("file_path") or inp.get("pattern") or ""
                    elif name == "Edit":
                        detail = inp.get("file_path", "")
                    elif name == "Write":
                        detail = inp.get("file_path", "")
                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        detail = cmd[:80]
                    elif name == "Task":
                        detail = inp.get("description", "")
                    if detail:
                        parts.append(f"\033[0;35m  [{name}: {detail}]\033[0m")
                    else:
                        parts.append(f"\033[0;35m  [{name}]\033[0m")

        # Final result
        if typ == "result":
            result = item.get("result", "")
            cost = item.get("total_cost_usd")
            turns = item.get("num_turns")
            duration = item.get("duration_ms")
            meta = []
            if turns:
                meta.append(f"{turns} turns")
            if duration:
                meta.append(f"{duration / 1000:.0f}s")
            if cost:
                meta.append(f"${cost:.2f}")
            header = ", ".join(meta) if meta else ""
            parts.append(f"\033[1;32m--- RESULT ({header}) ---\033[0m")
            parts.append(result)

    return "\n".join(parts) if parts else None


def format_line(line: str) -> str | None:
    stripped = line.rstrip()
    if not stripped:
        return None

    # Iteration headers and separators
    if stripped.startswith("=====") or stripped.startswith("-----"):
        return stripped
    if stripped.startswith("ITERATION "):
        return f"\033[1;33m{stripped}\033[0m"
    if stripped.startswith("cmd:"):
        return None  # skip verbose command line
    if stripped.startswith("started:"):
        return f"\033[0;37m  {stripped}\033[0m"
    if stripped.startswith("["):
        # Could be a timestamped event OR a JSON array
        if stripped.startswith("[{"):
            return parse_json_blob(stripped)
        # Timestamped event line
        return f"\033[0;36m{stripped}\033[0m"
    if stripped.startswith("--- exit="):
        return f"\033[0;37m{stripped}\033[0m"
    if stripped.startswith("{"):
        return parse_json_blob(stripped)

    # Prompt text lines (between cmd: and started:) — skip
    # They repeat every iteration and are noisy
    if any(stripped.startswith(p) for p in [
        "When you believe", "- What", "- Any", "Then output",
        "IMPORTANT:", "continue",
    ]):
        return None

    # Other plain text
    return stripped


def main():
    for line in sys.stdin:
        try:
            out = format_line(line)
            if out is not None:
                print(out, flush=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
