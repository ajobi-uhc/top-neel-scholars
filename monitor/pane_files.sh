#!/usr/bin/env bash
# Pane: tail -f a workspace files log (no refresh/flicker)
cd "$(dirname "$0")/.."
WS="${1:-$HOME/sandbox}"
LOGFILE="$WS/status/_files.log"

mkdir -p "$WS/status"
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# Helper: list workspace files sorted by mtime (newest first)
# Uses find -printf (Linux) for speed — no per-file subprocess.
list_files() {
    find "$WS" -type f \
        -not -path "*/.git/*" \
        -not -path "*/status/*" \
        -not -path "*/__pycache__/*" \
        -not -name "*.pyc" \
        -printf "%T@ %TY-%Tm-%Td %TH:%TM  %p\n" 2>/dev/null \
        | sort -rn | head -25 | cut -d' ' -f2- \
        | while read -r line; do
            echo "  $line"
        done
}

file_count() {
    find "$WS" -type f \
        -not -path "*/.git/*" \
        -not -path "*/status/*" \
        -not -path "*/__pycache__/*" \
        -not -name "*.pyc" 2>/dev/null | wc -l
}

# Seed the log with current file listing
: > "$LOGFILE"
{
    printf '=== WORKSPACE FILES ===\n\n'
    if [ -d "$WS" ]; then
        list_files

        echo ""
        printf '  %s files in workspace (excl. .git/, status/)\n' "$(file_count)"
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
                list_files

                echo ""
                printf '  %s files in workspace (excl. .git/, status/)\n' "$(file_count)"
            fi
        } >> "$LOGFILE"
    done
) &

exec tail -n +1 -f "$LOGFILE"
