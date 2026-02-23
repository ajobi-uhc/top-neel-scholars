"""Tests for src.rate_monitor — all use dependency injection, no network or real credentials."""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from src.rate_monitor import (
    RateMonitor,
    check_claude_usage,
    check_codex_usage,
    get_claude_token,
)


# --- get_claude_token ---

def test_get_claude_token_from_env():
    with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "tok-from-env"}):
        assert get_claude_token() == "tok-from-env"


def test_get_claude_token_from_file(tmp_path):
    creds = {"claudeAiOauth": {"accessToken": "tok-from-file"}}
    creds_path = tmp_path / ".credentials.json"
    creds_path.write_text(json.dumps(creds))

    with patch("src.rate_monitor.Path.home", return_value=tmp_path), \
         patch.dict(os.environ, {}, clear=True):
        # Need the file at tmp_path/.claude/.credentials.json
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        real_creds = claude_dir / ".credentials.json"
        real_creds.write_text(json.dumps(creds))

        token = get_claude_token()
        assert token == "tok-from-file"


def test_get_claude_token_missing(tmp_path):
    with patch("src.rate_monitor.Path.home", return_value=tmp_path), \
         patch.dict(os.environ, {}, clear=True):
        assert get_claude_token() is None


# --- check_claude_usage ---

def test_check_claude_usage_parses_response():
    response_data = {
        "five_hour": {"utilization": 45.0, "resets_at": "2026-02-23T09:00:00+00:00"},
        "seven_day": {"utilization": 30.0, "resets_at": "2026-02-26T00:00:00+00:00"},
    }

    class FakeResponse:
        def read(self):
            return json.dumps(response_data).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    result = check_claude_usage("fake-token", _urlopen=lambda req, timeout=10: FakeResponse())
    assert result["utilization"] == 45.0
    assert result["resets_at"] == "2026-02-23T09:00:00+00:00"


def test_check_claude_usage_uses_max_utilization():
    response_data = {
        "five_hour": {"utilization": 20.0, "resets_at": "2026-02-23T09:00:00+00:00"},
        "seven_day": {"utilization": 70.0, "resets_at": "2026-02-26T00:00:00+00:00"},
    }

    class FakeResponse:
        def read(self):
            return json.dumps(response_data).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    result = check_claude_usage("fake-token", _urlopen=lambda req, timeout=10: FakeResponse())
    assert result["utilization"] == 70.0
    assert result["resets_at"] == "2026-02-26T00:00:00+00:00"


# --- check_codex_usage ---

def test_check_codex_usage_parses_session(tmp_path):
    session_dir = tmp_path / "2026" / "02" / "23"
    session_dir.mkdir(parents=True)
    jsonl = session_dir / "rollout-2026-02-23T06-00-00-abc123.jsonl"

    events = [
        {"timestamp": "2026-02-23T06:00:00Z", "type": "event_msg", "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 42.5, "window_minutes": 10080, "resets_at": 1772427196},
                "secondary": None,
            },
        }},
        {"timestamp": "2026-02-23T06:01:00Z", "type": "event_msg", "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 55.0, "window_minutes": 10080, "resets_at": 1772427196},
                "secondary": None,
            },
        }},
    ]
    jsonl.write_text("\n".join(json.dumps(e) for e in events))

    result = check_codex_usage(_sessions_dir=str(tmp_path))
    assert result["utilization"] == 55.0  # last event wins
    assert result["resets_at"] == 1772427196


def test_check_codex_usage_no_sessions(tmp_path):
    result = check_codex_usage(_sessions_dir=str(tmp_path))
    assert result["utilization"] == 0.0
    assert result["resets_at"] is None


# --- RateMonitor ---

def test_monitor_no_pause_below_threshold():
    sleeps = []
    monitor = RateMonitor(
        provider="claude",
        threshold=80.0,
        _check_fn=lambda: {"utilization": 50.0, "resets_at": None},
        _sleep_fn=lambda s: sleeps.append(s),
    )
    monitor._enabled = True
    # Simulate one check cycle
    monitor._monitor_loop_once()
    assert not monitor._should_pause
    monitor.wait_if_needed()  # should return immediately
    assert len(sleeps) == 0


def test_monitor_pauses_at_threshold():
    monitor = RateMonitor(
        provider="claude",
        threshold=80.0,
        _check_fn=lambda: {"utilization": 85.0, "resets_at": None},
        _sleep_fn=lambda s: None,
    )
    monitor._enabled = True
    monitor._monitor_loop_once()
    assert monitor._should_pause
    assert monitor._last_utilization == 85.0


def test_monitor_waits_then_resumes():
    call_count = 0

    def check_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return {"utilization": 90.0, "resets_at": None}
        return {"utilization": 50.0, "resets_at": None}

    sleeps = []
    monitor = RateMonitor(
        provider="claude",
        threshold=80.0,
        check_interval=10.0,
        _check_fn=check_fn,
        _sleep_fn=lambda s: sleeps.append(s),
    )
    monitor._enabled = True
    monitor._monitor_loop_once()  # sets pause (90%)
    assert monitor._should_pause

    monitor.wait_if_needed()  # should sleep once, re-check (50%), then return
    assert len(sleeps) == 1
    assert sleeps[0] == 10.0  # check_interval since resets_at is None
    assert not monitor._should_pause


def test_monitor_caps_wait_at_check_interval():
    future_reset = time.time() + 99999  # way in the future
    sleeps = []

    call_count = 0
    def check_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return {"utilization": 95.0, "resets_at": future_reset}
        return {"utilization": 10.0, "resets_at": None}

    monitor = RateMonitor(
        provider="claude",
        threshold=80.0,
        check_interval=30.0,
        _check_fn=check_fn,
        _sleep_fn=lambda s: sleeps.append(s),
    )
    monitor._enabled = True
    monitor._monitor_loop_once()
    monitor.wait_if_needed()

    assert len(sleeps) == 1
    assert sleeps[0] == 30.0  # capped at check_interval, not resets_at


def test_monitor_handles_check_failure():
    def failing_check():
        raise ConnectionError("network down")

    monitor = RateMonitor(
        provider="claude",
        threshold=80.0,
        _check_fn=failing_check,
        _sleep_fn=lambda s: None,
    )
    monitor._enabled = True
    # Should not raise, should not set pause
    monitor._monitor_loop_once()
    assert not monitor._should_pause


def test_monitor_disabled_no_check_fn():
    monitor = RateMonitor(provider="claude", threshold=80.0)
    monitor._enabled = False
    # wait_if_needed should be a no-op
    monitor.wait_if_needed()
    assert not monitor._should_pause


# Helper: add _monitor_loop_once for testing without threads
# This is monkey-patched into the class for test convenience.
def _monitor_loop_once(self):
    """Run a single iteration of the monitor loop (for testing without threads)."""
    try:
        result = self._do_check()
        with self._lock:
            self._last_utilization = result["utilization"]
            if result["utilization"] >= self.threshold:
                self._should_pause = True
                self._update_pause_until(result)
            else:
                self._should_pause = False
                self._pause_until = None
    except Exception as e:
        pass  # matches graceful degradation behavior


RateMonitor._monitor_loop_once = _monitor_loop_once
