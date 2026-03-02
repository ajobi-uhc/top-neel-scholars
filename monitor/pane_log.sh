#!/usr/bin/env bash
# Pane: cat all log files then tail -f the latest (parsed for readability)
cd "$(dirname "$0")/.."
LOG_DIR="./logs"
PARSER="$(dirname "$0")/parse_log.py"

echo "Waiting for log file..."
while true; do
    files=$(ls -t "$LOG_DIR"/session_*.log 2>/dev/null)
    if [ -n "$files" ]; then
        # Print all log files oldest-first, then tail -f the newest
        all=$(echo "$files" | tac)
        latest=$(echo "$files" | head -1)
        echo "Showing all logs (parsed), tailing: $latest"
        # Cat all older files, then tail the latest from beginning
        for f in $all; do
            if [ "$f" != "$latest" ]; then
                cat "$f" 2>/dev/null
            fi
        done | python3 "$PARSER"
        exec tail -n +1 -f "$latest" | python3 "$PARSER"
    fi
    sleep 2
done
