#!/usr/bin/env bash
# Pane: show latest status JSON + worker markdown
cd "$(dirname "$0")/.."
STATUS_DIR="./workspace/status"

while true; do
    clear
    printf '\033[1;33m=== LATEST STATUS ===\033[0m\n\n'

    md=$(ls -t "$STATUS_DIR"/status_*.md 2>/dev/null | head -1)
    if [ -n "$md" ]; then
        printf '\033[1;36m--- Worker Status (%s) ---\033[0m\n' "$(basename "$md")"
        cat "$md" 2>/dev/null
        echo ""
    fi

    json=$(ls -t "$STATUS_DIR"/status_*.json 2>/dev/null | head -1)
    if [ -n "$json" ]; then
        printf '\033[1;32m--- Looper Status (%s) ---\033[0m\n' "$(basename "$json")"
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
" "$json" 2>/dev/null
        echo ""
    fi

    if [ -z "$md" ] && [ -z "$json" ]; then
        echo "  No status files yet in $STATUS_DIR"
        echo "  (start the agent with: python run.py)"
    fi

    n_json=$(ls "$STATUS_DIR"/status_*.json 2>/dev/null | wc -l)
    n_md=$(ls "$STATUS_DIR"/status_*.md 2>/dev/null | wc -l)
    printf '\033[0;37m  Total: %s iterations, %s worker status reports\033[0m\n' "$n_json" "$n_md"

    sleep 5
done
