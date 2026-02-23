#!/usr/bin/env bash
# tmux dashboard for monitoring the looper agent
# Usage: ./monitor.sh [session-name]
#   Launches a 4-pane tmux layout. Run "tmux attach -t <session>" if detached.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SESSION="${1:-looper-monitor}"
PANE_DIR="$ROOT/monitor"

# Kill existing session if any
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create session (detached, fixed size so splits work without a terminal)
tmux new-session -d -s "$SESSION" -x 200 -y 50 "bash $PANE_DIR/pane_log.sh"
sleep 0.5

# Style
tmux set-option -t "$SESSION" status-style "bg=colour235,fg=colour136"
tmux set-option -t "$SESSION" pane-border-style "fg=colour240"
tmux set-option -t "$SESSION" pane-active-border-style "fg=colour136"

# Split into 4 panes (avoid -p flag; broken in detached tmux 3.4)
tmux split-window -t "$SESSION"   -h "bash $PANE_DIR/pane_status.sh"
tmux split-window -t "$SESSION.0" -v "bash $PANE_DIR/pane_timeline.sh"
tmux split-window -t "$SESSION.2" -v "bash $PANE_DIR/pane_files.sh"

# Even 2x2 grid
tmux select-layout -t "$SESSION" tiled

# Attach if running interactively, otherwise just print instructions
if [ -t 0 ]; then
    exec tmux attach -t "$SESSION"
else
    echo "Dashboard created: tmux attach -t $SESSION"
fi
