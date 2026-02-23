"""Background usage monitor that checks API usage and pauses the loop before hitting rate limits.

Claude: polls GET https://api.anthropic.com/api/oauth/usage
Codex: reads ~/.codex/sessions/ JSONL files for rate_limits data
"""

import glob
import json
import os
import threading
import time
import urllib.request
from pathlib import Path


def get_claude_token() -> str | None:
    """Read OAuth token from env var or ~/.claude/.credentials.json."""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:
        return token
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if creds_path.exists():
        try:
            data = json.loads(creds_path.read_text())
            return data.get("claudeAiOauth", {}).get("accessToken")
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def check_claude_usage(token: str, _urlopen=None) -> dict:
    """Call the Claude OAuth usage API.

    Returns {"utilization": float (0-100), "resets_at": str | None}.
    Uses max of five_hour and seven_day utilization.
    """
    url = "https://api.anthropic.com/api/oauth/usage"
    req = urllib.request.Request(url, method="GET", headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "claude-code/2.0.32",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    })
    opener = _urlopen or urllib.request.urlopen
    with opener(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    utilization = 0.0
    resets_at = None
    for window in ("five_hour", "seven_day"):
        info = data.get(window)
        if info and info.get("utilization") is not None:
            if info["utilization"] > utilization:
                utilization = info["utilization"]
                resets_at = info.get("resets_at")

    return {"utilization": utilization, "resets_at": resets_at}


def check_codex_usage(_sessions_dir: str | None = None) -> dict:
    """Read the most recent Codex session JSONL for rate limit data.

    Returns {"utilization": float (0-100), "resets_at": float | None}.
    """
    sessions_dir = _sessions_dir or str(Path.home() / ".codex" / "sessions")
    pattern = os.path.join(sessions_dir, "**", "rollout-*.jsonl")
    files = glob.glob(pattern, recursive=True)
    if not files:
        return {"utilization": 0.0, "resets_at": None}

    latest = max(files, key=os.path.getmtime)
    last_token_event = None
    with open(latest) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                payload = obj.get("payload", {})
                if payload.get("type") == "token_count":
                    last_token_event = payload
            except json.JSONDecodeError:
                continue

    if not last_token_event:
        return {"utilization": 0.0, "resets_at": None}

    rate_limits = last_token_event.get("rate_limits", {})
    primary = rate_limits.get("primary", {})
    return {
        "utilization": primary.get("used_percent", 0.0),
        "resets_at": primary.get("resets_at"),
    }


class RateMonitor:
    """Background thread that periodically checks API usage and signals when to pause."""

    def __init__(
        self,
        provider: str,
        check_interval: float = 60.0,
        threshold: float = 95.0,
        max_wait: int = 3600,
        _check_fn=None,
        _sleep_fn=None,
    ):
        self.provider = provider
        self.check_interval = check_interval
        self.threshold = threshold
        self.max_wait = max_wait

        self._check_fn = _check_fn
        self._sleep_fn = _sleep_fn or time.sleep

        self._should_pause = False
        self._pause_until: float | None = None
        self._last_utilization: float = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.cancel_event = threading.Event()  # set to kill running subprocess
        self._thread: threading.Thread | None = None
        self._enabled = False

    def start(self):
        """Start the background monitoring thread."""
        if self._check_fn:
            self._enabled = True
        elif self.provider == "claude":
            self._enabled = get_claude_token() is not None
        elif self.provider == "codex":
            self._enabled = True  # session files always available
        else:
            self._enabled = False

        if not self._enabled:
            print("  [rate_monitor] no credentials found -- monitoring disabled")
            return

        # Do first check synchronously so pause flag is set before loop begins
        try:
            result = self._do_check()
            self._last_utilization = result["utilization"]
            if result["utilization"] >= self.threshold:
                self._should_pause = True
                self._update_pause_until(result)
            print(f"  [rate_monitor] started (threshold={self.threshold}%, interval={self.check_interval}s, current={result['utilization']:.1f}%)")
        except Exception as e:
            print(f"  [rate_monitor] started (threshold={self.threshold}%, interval={self.check_interval}s, initial check failed: {e})")

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the monitoring thread to stop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def wait_if_needed(self):
        """Block if usage is above threshold. Called from main loop before each iteration."""
        if not self._enabled:
            return

        while True:
            with self._lock:
                if not self._should_pause:
                    return
                pause_until = self._pause_until
                utilization = self._last_utilization

            wait_secs = 0.0
            if pause_until:
                wait_secs = pause_until - time.time()
            if wait_secs <= 0:
                wait_secs = self.check_interval

            wait_secs = min(wait_secs, self.check_interval)

            print(f"  [rate_monitor] usage at {utilization:.1f}% (>= {self.threshold}%) -- waiting {wait_secs:.0f}s")
            self._sleep_fn(wait_secs)

            # Re-check usage after sleeping
            try:
                result = self._do_check()
                with self._lock:
                    self._last_utilization = result["utilization"]
                    if result["utilization"] < self.threshold:
                        self._should_pause = False
                        self.cancel_event.clear()
                        print(f"  [rate_monitor] usage dropped to {result['utilization']:.1f}% -- resuming")
                        return
                    self._update_pause_until(result)
            except Exception:
                with self._lock:
                    self._should_pause = False
                self.cancel_event.clear()
                return

    def _monitor_loop(self):
        """Background loop: check usage, set/clear pause flag, sleep, repeat."""
        while not self._stop_event.is_set():
            try:
                result = self._do_check()
                with self._lock:
                    self._last_utilization = result["utilization"]
                    if result["utilization"] >= self.threshold:
                        if not self._should_pause:
                            print(f"  [rate_monitor] usage at {result['utilization']:.1f}% -- cancelling current iteration")
                        self._should_pause = True
                        self._update_pause_until(result)
                        self.cancel_event.set()  # kill running subprocess
                    else:
                        self._should_pause = False
                        self._pause_until = None
            except Exception as e:
                print(f"  [rate_monitor] check failed: {e}")

            self._stop_event.wait(self.check_interval)

    def _do_check(self) -> dict:
        """Run the appropriate usage checker."""
        if self._check_fn:
            return self._check_fn()
        if self.provider == "claude":
            token = get_claude_token()
            if not token:
                return {"utilization": 0.0, "resets_at": None}
            return check_claude_usage(token)
        elif self.provider == "codex":
            return check_codex_usage()
        return {"utilization": 0.0, "resets_at": None}

    def _update_pause_until(self, result: dict):
        """Set _pause_until from result's resets_at field."""
        resets_at = result.get("resets_at")
        if resets_at is None:
            self._pause_until = None
        elif isinstance(resets_at, (int, float)):
            self._pause_until = float(resets_at)
        elif isinstance(resets_at, str):
            # ISO 8601 timestamp — parse to unix time
            from datetime import datetime, timezone
            try:
                dt = datetime.fromisoformat(resets_at)
                self._pause_until = dt.timestamp()
            except ValueError:
                self._pause_until = None
