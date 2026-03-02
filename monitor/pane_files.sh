#!/usr/bin/env bash
# Pane: tail -f a workspace files log (no refresh/flicker, macOS compatible)
cd "$(dirname "$0")/.."
WS="./workspace"
LOGFILE="./workspace/status/_files.log"

mkdir -p "./workspace/status"

# Seed the log with current file listing
: > "$LOGFILE"
{
    printf '=== WORKSPACE FILES ===\n\n'
    if [ -d "$WS" ]; then
        find "$WS" -type f \
            -not -path "*/status/*" \
            -not -path "*/__pycache__/*" \
            -not -name "*.pyc" \
            -exec stat -f "%m %Sm  %N" -t "%Y-%m-%d %H:%M" {} \; 2>/dev/null \
            | sort -rn | head -25 | cut -d' ' -f2- \
            | while read -r line; do
                echo "  $line"
            done

        echo ""
        total=$(find "$WS" -type f -not -path "*/status/*" -not -name "*.pyc" 2>/dev/null | wc -l)
        printf '  %s files in workspace (excl. status/)\n' "$total"
    else
        echo "  Workspace not yet created."
    fi
} > "$LOGFILE"

# Background: periodically refresh the listing
(
    while true; do
        sleep 10
        {
            printf '\n--- Updated: %s ---\n\n' "$(date +%H:%M:%S)"
            if [ -d "$WS" ]; then
                find "$WS" -type f \
                    -not -path "*/status/*" \
                    -not -path "*/__pycache__/*" \
                    -not -name "*.pyc" \
                    -exec stat -f "%m %Sm  %N" -t "%Y-%m-%d %H:%M" {} \; 2>/dev/null \
                    | sort -rn | head -25 | cut -d' ' -f2- \
                    | while read -r line; do
                        echo "  $line"
                    done

                echo ""
                total=$(find "$WS" -type f -not -path "*/status/*" -not -name "*.pyc" 2>/dev/null | wc -l)
                printf '  %s files in workspace (excl. status/)\n' "$total"
            fi
        } >> "$LOGFILE"
    done
) &

exec tail -n +1 -f "$LOGFILE"
