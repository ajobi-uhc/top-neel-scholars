#!/usr/bin/env bash
# Pane: tail the most recent log file, parsed for readability
cd "$(dirname "$0")/.."
LOG_DIR="./logs"
PARSER="$(dirname "$0")/parse_log.py"

echo "Waiting for log file..."
while true; do
    f=$(ls -t "$LOG_DIR"/session_*.log 2>/dev/null | head -1)
    if [ -n "$f" ]; then
        echo "Tailing: $f (parsed)"
        exec tail -f "$f" | python3 "$PARSER"
    fi
    sleep 2
done
