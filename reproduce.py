#!/usr/bin/env python3
"""Reproduce the RIMBA paper tables and figures in a prepared environment."""
import argparse
import importlib.metadata
from pathlib import Path
import subprocess
import sys

from tools.reproduction.campaign import run


def parse_args(description: str = __doc__) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description, allow_abbrev=False)
    parser.add_argument("--diagnostic-frame-count", type=int, metavar="N", help="Use N frames per reconstructed sequence for a short diagnostic run.")
    parser.add_argument("--output", type=Path, metavar="PATH", help="Save results in a new directory at PATH.")
    parser.add_argument("--dry-run", action="store_true", help="Check prerequisites and print the planned commands without running experiments.")
    args = parser.parse_args()
    if args.diagnostic_frame_count is not None and args.diagnostic_frame_count < 1:
        parser.error("--diagnostic-frame-count must be positive")
    return args


if __name__ == "__main__":
    try:
        args = parse_args()
        run(Path(__file__).resolve().parent, args.output, args.diagnostic_frame_count, args.dry_run)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, importlib.metadata.PackageNotFoundError) as error:
        print(f"reproduce.py: {error}", file=sys.stderr)
        raise SystemExit(1)
