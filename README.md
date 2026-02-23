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
from looper import loop

# basic — run claude in a loop
loop("refactor the auth module to use JWT")

# use codex instead
loop("add unit tests for utils.py", provider="codex")

# custom timeout (seconds per iteration) and max loops
loop("fix all lint errors", timeout=600, max_loops=10)
```

## What it does

1. Runs `claude -p` (or `codex exec`) with your prompt
2. After each iteration, checks for:
   - **Timeout** — model took too long, probably stuck → retries
   - **Rate/usage limit** — waits and retries automatically
   - **Asking for input** — detects "would you like" / "shall I" patterns → retries
   - **No progress** — circuit breaker if output is identical 3x in a row → stops
   - **DONE signal** — model says it's finished → stops

## `loop()` parameters

| Param | Default | Description |
|-------|---------|-------------|
| `prompt` | required | The task to run |
| `provider` | `"claude"` | `"claude"` or `"codex"` |
| `timeout` | `900` | Seconds before killing a stuck iteration |
| `limit_wait` | `3600` | Seconds to sleep when rate limited |
| `max_loops` | `0` | Stop after N iterations. 0 = unlimited |
