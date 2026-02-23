"""Session logging — one log file per run."""

from datetime import datetime
from pathlib import Path


class Logger:
    def __init__(self, workspace: str):
        log_dir = Path(__file__).resolve().parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = log_dir / f"session_{stamp}.log"
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

    @property
    def file(self):
        """Return the underlying file object for streaming writes."""
        return self._f

    def _write(self, text: str):
        self._f.write(text + "\n")
        self._f.flush()

    def close(self):
        self._f.close()
