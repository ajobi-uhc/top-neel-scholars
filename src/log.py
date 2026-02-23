"""Always-on logging for looper sessions.

Opens one log file per session with full raw output from each iteration.
"""

from datetime import datetime
from pathlib import Path


class Logger:
    def __init__(self, workspace: str):
        log_dir = Path(workspace) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = log_dir / f"looper_{stamp}.log"
        self._f = open(self.path, "w")
        self.event(f"session started — log: {self.path}")

    def iteration_start(self, n: int, cmd: list[str]):
        self._write(f"\n{'='*60}")
        self._write(f"ITERATION {n}")
        self._write(f"cmd: {' '.join(cmd)}")
        self._write(f"started: {datetime.now().isoformat()}")
        self._write(f"{'='*60}\n")

    def iteration_output(self, raw: str, exit_code: int, elapsed: float):
        self._write(raw)
        self._write(f"\n--- exit={exit_code} elapsed={elapsed:.1f}s ---\n")

    def event(self, msg: str):
        self._write(f"[{datetime.now().isoformat()}] {msg}")

    def _write(self, text: str):
        self._f.write(text + "\n")
        self._f.flush()

    def close(self):
        self._f.close()
