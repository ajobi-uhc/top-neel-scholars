#!/usr/bin/env bash
# Pane: one-line-per-iteration timeline
cd "$(dirname "$0")/.."
STATUS_DIR="./workspace/status"

while true; do
    clear
    printf '\033[1;33m=== ITERATION TIMELINE ===\033[0m\n\n'

    found=0
    for f in $(ls -t "$STATUS_DIR"/status_*.json 2>/dev/null | tac); do
        found=1
        python3 -c "
import json, sys
with open(sys.argv[1]) as fh:
    d = json.load(fh)
it = d.get('iteration', '?')
ev = d.get('event', '?')
ec = d.get('exit_code', '?')
el = d.get('elapsed_seconds', '?')
ts = str(d.get('timestamp', '?'))[:19]
icons = {'ok': '\033[1;32m✓\033[0m', 'timeout': '\033[1;31m⏱\033[0m', 'rate_limit': '\033[1;33m⚠\033[0m', 'session_limit': '\033[1;33m⚠\033[0m', 'asked_input': '\033[1;35m?\033[0m', 'error': '\033[1;31m✗\033[0m'}
icon = icons.get(ev, '·')
print(f'  {icon} iter {it:>3}  {ev:<15} exit={ec}  {el:>6}s  {ts}')
" "$f" 2>/dev/null
    done

    if [ "$found" -eq 0 ]; then
        echo "  No iterations yet."
    fi

    sleep 5
done
