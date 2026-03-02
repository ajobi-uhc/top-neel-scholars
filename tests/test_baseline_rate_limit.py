"""Tests for rate limiting in the baseline script."""

import json
from unittest.mock import MagicMock, patch

from run_baseline import baseline


def _fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
    """Simulate a successful run_once that returns valid JSON output."""
    result = json.dumps({
        "type": "result",
        "session_id": "test-session",
        "result": "Done.",
    })
    return result, 0, 1.0


def _fake_run_once_rate_limited(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
    """Simulate a run_once cancelled by rate monitor (exit code 125)."""
    return "", 125, 0.5


# Codex JSONL output helpers

def _codex_success_output():
    """Simulate successful codex exec --json JSONL output."""
    lines = [
        json.dumps({"type": "thread.started", "thread_id": "test-thread"}),
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": "Done."}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 50}}),
    ]
    return "\n".join(lines)


def test_baseline_pauses_on_high_usage(tmp_path):
    """When usage exceeds threshold, the monitor should pause and the baseline
    should handle exit code 125 (rate-limited) then retry."""
    call_count = 0

    def fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call gets cancelled by rate monitor
            return "", 125, 0.5
        # Second call succeeds
        result = json.dumps({
            "type": "result",
            "session_id": "test-session",
            "result": "Done.",
        })
        return result, 0, 1.0

    check_count = 0

    def fake_check():
        nonlocal check_count
        check_count += 1
        if check_count <= 2:
            return {"utilization": 99.0, "resets_at": None}
        return {"utilization": 10.0, "resets_at": None}

    with patch("run_baseline.run_once", side_effect=fake_run_once), \
         patch("run_baseline.Logger") as MockLogger, \
         patch("run_baseline.RateMonitor") as MockMonitor:

        mock_logger = MagicMock()
        mock_logger.path = tmp_path / "test.log"
        mock_logger.file = MagicMock()
        MockLogger.return_value = mock_logger

        # Use a real RateMonitor with injected check function
        from src.rate_monitor import RateMonitor
        real_monitor = RateMonitor(
            provider="claude",
            threshold=95.0,
            check_interval=0.01,
            _check_fn=fake_check,
            _sleep_fn=lambda s: None,
        )
        MockMonitor.return_value = real_monitor

        baseline(
            "test prompt",
            max_turns=1,
            workspace=str(tmp_path),
        )

    # run_once was called twice: once rate-limited (125), once successful
    assert call_count == 2


def test_baseline_no_pause_below_threshold(tmp_path):
    """When usage is below threshold, baseline runs normally without pausing."""
    call_count = 0

    def fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
        nonlocal call_count
        call_count += 1
        result = json.dumps({
            "type": "result",
            "session_id": "test-session",
            "result": "Done.",
        })
        return result, 0, 1.0

    with patch("run_baseline.run_once", side_effect=fake_run_once), \
         patch("run_baseline.Logger") as MockLogger, \
         patch("run_baseline.RateMonitor") as MockMonitor:

        mock_logger = MagicMock()
        mock_logger.path = tmp_path / "test.log"
        mock_logger.file = MagicMock()
        MockLogger.return_value = mock_logger

        from src.rate_monitor import RateMonitor
        real_monitor = RateMonitor(
            provider="claude",
            threshold=95.0,
            _check_fn=lambda: {"utilization": 30.0, "resets_at": None},
            _sleep_fn=lambda s: None,
        )
        MockMonitor.return_value = real_monitor

        baseline(
            "test prompt",
            max_turns=2,
            workspace=str(tmp_path),
        )

    # Both turns ran without rate-limit retries
    assert call_count == 2


def test_baseline_retries_on_rate_limit_without_counting_turn(tmp_path):
    """Exit code 125 should NOT consume a turn — the turn counter should
    decrement so the same turn is retried."""
    calls = []

    def fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
        calls.append(cmd)
        if len(calls) <= 2:
            return "", 125, 0.5
        result = json.dumps({
            "type": "result",
            "session_id": "test-session",
            "result": "Done.",
        })
        return result, 0, 1.0

    with patch("run_baseline.run_once", side_effect=fake_run_once), \
         patch("run_baseline.Logger") as MockLogger, \
         patch("run_baseline.RateMonitor") as MockMonitor:

        mock_logger = MagicMock()
        mock_logger.path = tmp_path / "test.log"
        mock_logger.file = MagicMock()
        MockLogger.return_value = mock_logger

        from src.rate_monitor import RateMonitor
        real_monitor = RateMonitor(
            provider="claude",
            threshold=95.0,
            _check_fn=lambda: {"utilization": 10.0, "resets_at": None},
            _sleep_fn=lambda s: None,
        )
        MockMonitor.return_value = real_monitor

        baseline(
            "test prompt",
            max_turns=1,
            workspace=str(tmp_path),
        )

    # 2 rate-limited calls + 1 successful = 3 total, but only 1 turn consumed
    assert len(calls) == 3


# --- Codex provider tests ---


def test_codex_baseline_pauses_on_high_usage(tmp_path):
    """Codex: when usage exceeds threshold, the monitor should pause and the
    baseline should handle exit code 125 (rate-limited) then retry."""
    call_count = 0

    def fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "", 125, 0.5
        return _codex_success_output(), 0, 1.0

    check_count = 0

    def fake_check():
        nonlocal check_count
        check_count += 1
        if check_count <= 2:
            return {"utilization": 99.0, "resets_at": None}
        return {"utilization": 10.0, "resets_at": None}

    with patch("run_baseline.run_once", side_effect=fake_run_once), \
         patch("run_baseline.extract_codex_session_id", return_value="codex-sess-1"), \
         patch("run_baseline.Logger") as MockLogger, \
         patch("run_baseline.RateMonitor") as MockMonitor:

        mock_logger = MagicMock()
        mock_logger.path = tmp_path / "test.log"
        mock_logger.file = MagicMock()
        MockLogger.return_value = mock_logger

        from src.rate_monitor import RateMonitor
        real_monitor = RateMonitor(
            provider="codex",
            threshold=95.0,
            check_interval=0.01,
            _check_fn=fake_check,
            _sleep_fn=lambda s: None,
        )
        MockMonitor.return_value = real_monitor

        baseline(
            "test prompt",
            provider="codex",
            max_turns=1,
            workspace=str(tmp_path),
        )

    assert call_count == 2


def test_codex_baseline_no_pause_below_threshold(tmp_path):
    """Codex: when usage is below threshold, baseline runs normally."""
    call_count = 0

    def fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
        nonlocal call_count
        call_count += 1
        return _codex_success_output(), 0, 1.0

    with patch("run_baseline.run_once", side_effect=fake_run_once), \
         patch("run_baseline.extract_codex_session_id", return_value="codex-sess-1"), \
         patch("run_baseline.Logger") as MockLogger, \
         patch("run_baseline.RateMonitor") as MockMonitor:

        mock_logger = MagicMock()
        mock_logger.path = tmp_path / "test.log"
        mock_logger.file = MagicMock()
        MockLogger.return_value = mock_logger

        from src.rate_monitor import RateMonitor
        real_monitor = RateMonitor(
            provider="codex",
            threshold=95.0,
            _check_fn=lambda: {"utilization": 30.0, "resets_at": None},
            _sleep_fn=lambda s: None,
        )
        MockMonitor.return_value = real_monitor

        baseline(
            "test prompt",
            provider="codex",
            max_turns=2,
            workspace=str(tmp_path),
        )

    assert call_count == 2


def test_codex_baseline_retries_on_rate_limit_without_counting_turn(tmp_path):
    """Codex: exit code 125 should NOT consume a turn."""
    calls = []

    def fake_run_once(cmd, timeout, cwd=None, log_file=None, cancel_event=None, quiet=False):
        calls.append(cmd)
        if len(calls) <= 2:
            return "", 125, 0.5
        return _codex_success_output(), 0, 1.0

    with patch("run_baseline.run_once", side_effect=fake_run_once), \
         patch("run_baseline.extract_codex_session_id", return_value="codex-sess-1"), \
         patch("run_baseline.Logger") as MockLogger, \
         patch("run_baseline.RateMonitor") as MockMonitor:

        mock_logger = MagicMock()
        mock_logger.path = tmp_path / "test.log"
        mock_logger.file = MagicMock()
        MockLogger.return_value = mock_logger

        from src.rate_monitor import RateMonitor
        real_monitor = RateMonitor(
            provider="codex",
            threshold=95.0,
            _check_fn=lambda: {"utilization": 10.0, "resets_at": None},
            _sleep_fn=lambda s: None,
        )
        MockMonitor.return_value = real_monitor

        baseline(
            "test prompt",
            provider="codex",
            max_turns=1,
            workspace=str(tmp_path),
        )

    assert len(calls) == 3
