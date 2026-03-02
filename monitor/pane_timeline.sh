#!/usr/bin/env bash
# Pane: tail -f a timeline log (no refresh/flicker)
cd "$(dirname "$0")/.."
WORKSPACE="${1:-$HOME/sandbox}"
STATUS_DIR="$WORKSPACE/status"
LOGFILE="$STATUS_DIR/_timeline.log"

mkdir -p "$STATUS_DIR"
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# Reset the log and seed with all existing iterations (oldest first)
: > "$LOGFILE"
for f in $(ls "$STATUS_DIR"/status_*.json 2>/dev/null | sort); do
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
" "$f" >> "$LOGFILE" 2>/dev/null
done

# Background: watch for new status files and append to the log
(
    LAST_JSON=$(ls "$STATUS_DIR"/status_*.json 2>/dev/null | sort | tail -1)
    while true; do
        json=$(ls -t "$STATUS_DIR"/status_*.json 2>/dev/null | head -1)

        if [ -n "$json" ] && [ "$json" != "$LAST_JSON" ]; then
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
" "$json" >> "$LOGFILE" 2>/dev/null
            LAST_JSON="$json"
        fi

        sleep 5
    done
) &

exec tail -n +1 -f "$LOGFILE"
