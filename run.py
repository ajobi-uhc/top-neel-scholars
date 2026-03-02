import argparse
import shutil
import subprocess
from pathlib import Path

from src import loop

SANDBOX_REPO = "https://github.com/divanoval/top-scholar-sandbox.git"
SANDBOX_DIR = Path(__file__).resolve().parent / "sandbox"

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
parser.add_argument("--model", type=str, default=None,
                    help="Model to use (e.g. claude-haiku-4-5-20251001)")
parser.add_argument("--rate-threshold", type=float, default=95.0,
                    help="Pause when usage %% exceeds this (0-100). Set low to test.")
args = parser.parse_args()

TASK = """\
Build a small Python CLI tool in src/wordfreq.py that:
1. Reads a text file passed as a CLI argument
2. Counts word frequencies (case-insensitive, strip punctuation)
3. Prints the top 10 most common words with their counts
4. Write tests in tests/test_wordfreq.py and make sure they pass
5. Create a sample input file at data/sample.txt with a few paragraphs of text
6. Run the tool on the sample file and verify it works

This should take multiple iterations — get the core logic working first, then tests, then polish.
"""

# Clone sandbox repo fresh each run
print(f"Cloning {SANDBOX_REPO} ...")
if SANDBOX_DIR.exists():
    shutil.rmtree(SANDBOX_DIR)
subprocess.run(["git", "clone", SANDBOX_REPO, str(SANDBOX_DIR)], check=True)
print(f"Cloned to {SANDBOX_DIR}")
print("-" * 60)

loop(TASK, provider=args.provider, model=args.model,
     timeout=120, rate_threshold=args.rate_threshold,
     workspace=str(SANDBOX_DIR))
