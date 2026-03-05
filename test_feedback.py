"""Quick test: does the feedback agent actually produce output?

Run from outside a claude session:
    cd /workspace/top-neel-scholars && python test_feedback.py
"""
import sys
import time
from pathlib import Path

# Make src importable
sys.path.insert(0, str(Path(__file__).parent))

from src.status import init_feedback_agent, run_feedback_agent_cc, find_latest_checkpoint

WORKSPACE = "/home/claude/sandbox"

print("=" * 60)
print("FEEDBACK AGENT TEST")
print("=" * 60)

# 1. Check that a finished file exists to evaluate
finished = find_latest_checkpoint(WORKSPACE, "finished")
if not finished:
    print("ERROR: No memories/finished_*.md found in workspace")
    sys.exit(1)
print(f"[ok] Found finished file: {finished.name}")
print(f"     Size: {finished.stat().st_size} bytes")

# 2. Init the feedback agent (creates a new session)
print("\n--- Step 1: Init feedback agent ---")
t0 = time.time()
session_id = init_feedback_agent(WORKSPACE, timeout=300)
print(f"  elapsed: {time.time() - t0:.1f}s")
if not session_id:
    print("ERROR: init_feedback_agent returned no session_id")
    sys.exit(1)
print(f"[ok] Feedback agent session: {session_id}")

# 3. Run feedback on the finished file
print(f"\n--- Step 2: Run feedback on {finished.name} ---")
t0 = time.time()
feedback_path, new_session_id = run_feedback_agent_cc(
    WORKSPACE,
    finished_path=finished,
    feedback_session_id=session_id,
    timeout=600,
)
elapsed = time.time() - t0
print(f"  elapsed: {elapsed:.1f}s")

if not feedback_path:
    print("FAIL: No feedback file produced!")
    sys.exit(1)

print(f"[ok] Feedback written to: {feedback_path}")
print(f"     Size: {feedback_path.stat().st_size} bytes")
print(f"\n--- Feedback preview (first 80 lines) ---")
lines = feedback_path.read_text().splitlines()
for line in lines[:80]:
    print(line)
if len(lines) > 80:
    print(f"... ({len(lines) - 80} more lines)")

print("\n" + "=" * 60)
print("TEST PASSED")
print("=" * 60)
