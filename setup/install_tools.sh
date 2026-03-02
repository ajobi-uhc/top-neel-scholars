#!/usr/bin/env bash
# Install Claude Code and Codex CLI on a fresh Ubuntu machine.
# Run as a user with sudo access: bash setup/install_tools.sh
set -euo pipefail

echo "=== Installing Node.js 20 ==="
if command -v node &>/dev/null && [[ "$(node --version)" == v20* ]]; then
    echo "Node.js $(node --version) already installed, skipping."
else
    sudo apt-get update -qq
    sudo apt-get install -y -qq nodejs npm
    sudo npm install -g n
    sudo n 20
    hash -r
fi
echo "node $(node --version)  npm $(npm --version)"

echo ""
echo "=== Installing Claude Code ==="
if command -v claude &>/dev/null; then
    echo "Claude Code already installed: $(claude --version 2>&1 | head -1)"
else
    sudo npm install -g @anthropic-ai/claude-code
    echo "Installed: $(claude --version 2>&1 | head -1)"
fi

echo ""
echo "=== Installing Codex CLI ==="
if command -v codex &>/dev/null; then
    echo "Codex CLI already installed: $(codex --version 2>&1 | head -1)"
else
    sudo npm install -g @openai/codex
    echo "Installed: $(codex --version 2>&1 | head -1)"
fi

echo ""
echo "=== Done ==="
echo "Next steps:"
echo "  - Claude: run 'claude' to authenticate (OAuth login)"
echo "  - Codex:  set CODEX_API_KEY env var or run 'codex' to configure"
