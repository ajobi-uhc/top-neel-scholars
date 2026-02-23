# looper

Run Claude Code or Codex in a loop with automatic stuck/limit detection.

No dependencies. Just Python 3.10+ and `claude` or `codex` CLI installed.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```python
from src import loop

# basic — run claude in a loop
loop("refactor the auth module to use JWT")

# use codex instead
loop("add unit tests for utils.py", provider="codex")

# custom timeout (seconds per iteration)
loop("fix all lint errors", timeout=600)
```

## What it does

1. Runs `claude -p` (or `codex exec`) with your prompt
2. A **background thread** monitors usage % and pauses before hitting rate limits:
   - **Claude**: polls `api.anthropic.com/api/oauth/usage` (reads token from `~/.claude/.credentials.json`)
   - **Codex**: reads `~/.codex/sessions/` JSONL files for rate limit data
3. After each iteration, checks for:
   - **Timeout** — model took too long, probably stuck → retries
   - **Asking for input** — detects "would you like" / "shall I" patterns → retries
   - **Non-zero exit** — retries automatically

## `loop()` parameters

| Param | Default | Description |
|-------|---------|-------------|
| `prompt` | required | The task to run |
| `provider` | `"claude"` | `"claude"` or `"codex"` |
| `timeout` | `900` | Seconds before killing a stuck iteration |
| `max_wait` | `3600` | Max seconds to sleep when rate limited |
| `rate_check_interval` | `60.0` | Seconds between usage checks |
| `rate_threshold` | `95.0` | Pause when usage % exceeds this (0-100) |

## Testing rate limits

Set a low threshold to trigger pausing immediately:

```bash
python run.py --provider claude --rate-threshold 1.0
```
