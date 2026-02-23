import argparse
from src import loop

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
parser.add_argument("--rate-threshold", type=float, default=95.0,
                    help="Pause when usage %% exceeds this (0-100). Set low to test.")
args = parser.parse_args()

loop("do a little mini project for neels sprint", provider=args.provider, timeout=30,
     rate_threshold=args.rate_threshold)
