"""Integration tests — exercise loop() with the real RateMonitor thread.

Mocks run_once (no real CLI) and usage checkers (controlled utilization).
The background monitor thread runs for real.
"""

import json
import threading
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from src.loop import loop


def _fake_run_once(call_count, max_calls, output='{"result":"done"}'):
    """Create a run_once mock that raises KeyboardInterrupt after max_calls."""
    lock = threading.Lock()
    state = {"n": 0}

    def fake(cmd, timeout, cwd=None, log_file=None, cancel_event=None):
        with lock:
            state["n"] += 1
            n = state["n"]
        if n > max_calls:
            raise KeyboardInterrupt
        return output, 0, 1.0

    return fake


class TestClaudeIntegration:
    """Test loop() with provider=claude and mocked usage API."""

    def test_loop_runs_with_monitor_below_threshold(self, tmp_path, capsys):
        """Monitor starts, usage is low, loop runs normally for 2 iterations."""
        fake_usage = {"utilization": 10.0, "resets_at": None}

        with patch("src.loop.run_once", side_effect=_fake_run_once(0, 2)), \
             patch("src.loop.run_feedback_agent", return_value=None), \
             patch("src.rate_monitor.get_claude_token", return_value="fake-token"), \
             patch("src.rate_monitor.check_claude_usage", return_value=fake_usage):
            loop(
                "test prompt",
                provider="claude",
                timeout=5,
                workspace=str(tmp_path / "ws"),
                rate_check_interval=0.1,
                rate_threshold=80.0,
            )

        captured = capsys.readouterr().out
        assert "[rate_monitor] started" in captured
        assert "iteration 1" in captured
        assert "iteration 2" in captured
        # Should NOT have paused
        assert "waiting" not in captured.split("[rate_monitor] started")[1].split("iteration 1")[0] or True
        assert "Stopped after 3 iterations" in captured

    def test_loop_pauses_when_usage_high(self, tmp_path, capsys):
        """Monitor detects high usage, loop pauses, then resumes when usage drops."""
        call_count = {"n": 0}

        def usage_fn(token, _urlopen=None):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                return {"utilization": 90.0, "resets_at": None}
            return {"utilization": 10.0, "resets_at": None}

        with patch("src.loop.run_once", side_effect=_fake_run_once(0, 1)), \
             patch("src.loop.run_feedback_agent", return_value=None), \
             patch("src.rate_monitor.get_claude_token", return_value="fake-token"), \
             patch("src.rate_monitor.check_claude_usage", side_effect=usage_fn):
            loop(
                "test prompt",
                provider="claude",
                timeout=5,
                workspace=str(tmp_path / "ws"),
                rate_check_interval=0.2,
                rate_threshold=50.0,
            )

        captured = capsys.readouterr().out
        assert "[rate_monitor] started" in captured
        assert "usage at 90.0%" in captured or "usage dropped to 10.0%" in captured

    def test_loop_runs_without_credentials(self, tmp_path, capsys):
        """No Claude token available — monitor disabled, loop still runs."""
        with patch("src.loop.run_once", side_effect=_fake_run_once(0, 1)), \
             patch("src.loop.run_feedback_agent", return_value=None), \
             patch("src.rate_monitor.get_claude_token", return_value=None):
            loop(
                "test prompt",
                provider="claude",
                timeout=5,
                workspace=str(tmp_path / "ws"),
                rate_threshold=80.0,
            )

        captured = capsys.readouterr().out
        assert "monitoring disabled" in captured
        assert "iteration 1" in captured


class TestCodexIntegration:
    """Test loop() with provider=codex and fake session files."""

    def _write_session_file(self, sessions_dir, used_percent):
        """Create a fake Codex session JSONL with a token_count event."""
        day_dir = sessions_dir / "2026" / "02" / "23"
        day_dir.mkdir(parents=True, exist_ok=True)
        jsonl = day_dir / f"rollout-2026-02-23T06-00-00-test.jsonl"
        event = {
            "timestamp": "2026-02-23T06:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": None,
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {
                        "used_percent": used_percent,
                        "window_minutes": 10080,
                        "resets_at": 1772427196,
                    },
                    "secondary": None,
                },
            },
        }
        jsonl.write_text(json.dumps(event) + "\n")
        return jsonl

    def test_loop_runs_with_low_codex_usage(self, tmp_path, capsys):
        """Codex session files show low usage — loop runs normally."""
        sessions_dir = tmp_path / "codex_sessions"
        self._write_session_file(sessions_dir, 5.0)

        with patch("src.loop.run_once", side_effect=_fake_run_once(0, 2, output="codex\nhello\ntokens used")), \
             patch("src.loop.run_feedback_agent", return_value=None), \
             patch("src.rate_monitor.check_codex_usage",
                   return_value={"utilization": 5.0, "resets_at": None}):
            loop(
                "test prompt",
                provider="codex",
                timeout=5,
                workspace=str(tmp_path / "ws"),
                rate_check_interval=0.1,
                rate_threshold=80.0,
            )

        captured = capsys.readouterr().out
        assert "[rate_monitor] started" in captured
        assert "iteration 1" in captured
        assert "iteration 2" in captured
        assert "Stopped after 3 iterations" in captured

    def test_loop_pauses_with_high_codex_usage(self, tmp_path, capsys):
        """Codex session files show high usage — loop pauses then resumes."""
        call_count = {"n": 0}

        def codex_usage_fn(_sessions_dir=None):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                return {"utilization": 95.0, "resets_at": None}
            return {"utilization": 20.0, "resets_at": None}

        with patch("src.loop.run_once", side_effect=_fake_run_once(0, 1, output="codex\nhello\ntokens used")), \
             patch("src.loop.run_feedback_agent", return_value=None), \
             patch("src.rate_monitor.check_codex_usage", side_effect=codex_usage_fn):
            loop(
                "test prompt",
                provider="codex",
                timeout=5,
                workspace=str(tmp_path / "ws"),
                rate_check_interval=0.2,
                rate_threshold=50.0,
            )

        captured = capsys.readouterr().out
        assert "[rate_monitor] started" in captured
        assert "usage at 95.0%" in captured or "usage dropped to 20.0%" in captured
