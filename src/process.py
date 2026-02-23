"""Subprocess management for looper.

Handles building commands and running them with proper ctrl+c handling.
"""

import os
import signal
import subprocess
import time
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Tracks the currently running child so the signal handler can kill it
_current_proc: subprocess.Popen | None = None


def _sigint_handler(signum, frame):
    """Kill the child process with SIGKILL and exit immediately."""
    if _current_proc and _current_proc.poll() is None:
        try:
            os.kill(_current_proc.pid, signal.SIGKILL)
        except OSError:
            pass
    raise KeyboardInterrupt


# Install once on import
signal.signal(signal.SIGINT, _sigint_handler)


def build_cmd(provider: str, prompt: str, session_id: str | None = None) -> list[str]:
    preamble = (PROMPTS_DIR / "worker_preamble.md").read_text()
    full_prompt = preamble + "\n" + prompt

    if provider == "claude":
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--verbose",
        ]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", full_prompt]
        return cmd
    elif provider == "codex":
        return ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", full_prompt]
    else:
        raise ValueError(f"Unknown provider: {provider}")


def run_once(cmd: list[str], timeout: int, cwd: str | None = None) -> tuple[str, int, float]:
    """Run a single iteration. Returns (output, exit_code, elapsed).

    exit_code 124 = timed out.
    """
    global _current_proc
    start = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )
    _current_proc = proc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        elapsed = time.time() - start
        return stdout + stderr, proc.returncode, elapsed
    except subprocess.TimeoutExpired:
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
        elapsed = time.time() - start
        stdout = proc.stdout.read() if proc.stdout else ""
        stderr = proc.stderr.read() if proc.stderr else ""
        return stdout + stderr, 124, elapsed
    except KeyboardInterrupt:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait()
        raise
    finally:
        _current_proc = None
