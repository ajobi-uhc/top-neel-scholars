import argparse
from src import loop

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
args = parser.parse_args()

loop("do a little mini project for neels sprint", provider=args.provider, timeout=30)
