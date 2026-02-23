"""Subprocess management — run commands with live terminal output."""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def build_cmd(provider: str, prompt: str, session_id: str | None = None, model: str | None = None) -> list[str]:
    preamble = (PROMPTS_DIR / "worker_preamble.md").read_text()
    full_prompt = preamble + "\n" + prompt

    if provider == "claude":
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--verbose",
        ]
        if model:
            cmd += ["--model", model]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", full_prompt]
        return cmd
    elif provider == "codex":
        if session_id:
            return ["codex", "exec", "resume", session_id, "--dangerously-bypass-approvals-and-sandbox"]
        return ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", full_prompt]
    else:
        raise ValueError(f"Unknown provider: {provider}")


def run_once(cmd: list[str], timeout: int, cwd: str | None = None, log_file=None,
             cancel_event=None) -> tuple[str, int, float]:
    """Run a single iteration with live terminal output.

    Child runs in its own session so ctrl+c only hits the parent.
    Parent catches KeyboardInterrupt and SIGKILLs the child.
    Returns (output, exit_code, elapsed).
    exit_code 124 = timed out, 125 = cancelled by rate monitor.
    """
    start = time.time()
    output_lines = []

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        start_new_session=True,  # isolate child from ctrl+c
    )

    # Watcher thread: kills the subprocess when cancel_event is set
    def _cancel_watcher():
        cancel_event.wait()
        if proc.poll() is None:  # still running
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass

    if cancel_event:
        watcher = threading.Thread(target=_cancel_watcher, daemon=True)
        watcher.start()

    try:
        for line in proc.stdout:
            sys.stdout.write(f"  {line}")
            sys.stdout.flush()
            if log_file:
                log_file.write(line)
                log_file.flush()
            output_lines.append(line)

        proc.wait(timeout=timeout)
        elapsed = time.time() - start

        # Check if we were cancelled (process got SIGTERM from watcher)
        if cancel_event and cancel_event.is_set():
            return "".join(output_lines), 125, elapsed

        return "".join(output_lines), proc.returncode, elapsed

    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        elapsed = time.time() - start
        return "".join(output_lines), 124, elapsed

    except KeyboardInterrupt:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        raise
