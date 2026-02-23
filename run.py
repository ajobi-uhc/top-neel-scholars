import argparse
from looper import loop

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
args = parser.parse_args()

loop("say hello world and nothing else", provider=args.provider, max_loops=2, timeout=30)
