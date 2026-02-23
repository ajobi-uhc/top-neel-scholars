#!/usr/bin/env bash
# Pane: recently modified workspace files
cd "$(dirname "$0")/.."
WS="./workspace"

while true; do
    clear
    printf '\033[1;33m=== WORKSPACE FILES ===\033[0m\n\n'

    if [ -d "$WS" ]; then
        find "$WS" -type f \
            -not -path "*/status/*" \
            -not -path "*/__pycache__/*" \
            -not -name "*.pyc" \
            -printf "%T@ %Tc  %P\n" 2>/dev/null \
            | sort -rn | head -25 | cut -d" " -f2- \
            | while read -r line; do
                echo "  $line"
            done

        echo ""
        total=$(find "$WS" -type f -not -path "*/status/*" -not -name "*.pyc" 2>/dev/null | wc -l)
        printf '\033[0;37m  %s files in workspace (excl. status/)\033[0m\n' "$total"
    else
        echo "  Workspace not yet created."
    fi

    sleep 10
done
