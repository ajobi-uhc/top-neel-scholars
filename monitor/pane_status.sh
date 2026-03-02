#!/usr/bin/env bash
# Pane: tail -f a status log (no refresh/flicker)
cd "$(dirname "$0")/.."
WORKSPACE="${1:-$HOME/sandbox}"
STATUS_DIR="$WORKSPACE/status"
LOGFILE="$STATUS_DIR/_status.log"

mkdir -p "$STATUS_DIR"
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# Helper to format a status JSON file
format_json() {
    python3 -c "
import json, sys
with open(sys.argv[1]) as fh:
    d = json.load(fh)
print(f'  Iteration:  {d.get(\"iteration\", \"?\")}')
print(f'  Event:      {d.get(\"event\", \"?\")}')
print(f'  Exit code:  {d.get(\"exit_code\", \"?\")}')
print(f'  Elapsed:    {d.get(\"elapsed_seconds\", \"?\")}s')
sid = d.get('session_id') or 'none'
print(f'  Session:    {sid[:30]}')
print(f'  Timestamp:  {d.get(\"timestamp\", \"?\")}')
tail = d.get('output_tail', '')
if tail:
    lines = tail.strip().splitlines()
    print(f'  Output tail ({len(lines)} lines):')
    for l in lines[-10:]:
        print(f'    {l[:120]}')
" "$1" 2>/dev/null
}

# Reset and seed with all existing status files (oldest first)
: > "$LOGFILE"
for f in $(ls "$STATUS_DIR"/status_*.json 2>/dev/null | sort); do
    {
        # Find matching .md (same timestamp suffix)
        base=$(basename "$f" .json)
        md_file="$STATUS_DIR/${base}.md"
        if [ -f "$md_file" ]; then
            echo "--- Worker Status (${base}.md) ---"
            cat "$md_file" 2>/dev/null
            echo ""
        fi
        echo "--- Looper Status ($(basename "$f")) ---"
        format_json "$f"
        echo ""
    } >> "$LOGFILE"
done

# Background: watch for new status files and append to the log
(
    LAST_JSON=$(ls "$STATUS_DIR"/status_*.json 2>/dev/null | sort | tail -1)
    LAST_MD=$(ls "$STATUS_DIR"/status_*.md 2>/dev/null | sort | tail -1)
    while true; do
        md=$(ls "$STATUS_DIR"/status_*.md 2>/dev/null | sort | tail -1)
        json=$(ls "$STATUS_DIR"/status_*.json 2>/dev/null | sort | tail -1)

        if [ -n "$md" ] && [ "$md" != "$LAST_MD" ]; then
            {
                echo "--- Worker Status ($(basename "$md")) ---"
                cat "$md" 2>/dev/null
                echo ""
            } >> "$LOGFILE"
            LAST_MD="$md"
        fi

        if [ -n "$json" ] && [ "$json" != "$LAST_JSON" ]; then
            {
                echo "--- Looper Status ($(basename "$json")) ---"
                format_json "$json"
                echo ""
            } >> "$LOGFILE"
            LAST_JSON="$json"
        fi

        sleep 5
    done
) &

exec tail -n +1 -f "$LOGFILE"
