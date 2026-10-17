#!/usr/bin/env python3
"""Reproduce the five external methods used in the RIMBA paper."""
from pathlib import Path
import subprocess
import sys

from reproduce import parse_args
from external.campaign import run


if __name__ == "__main__":
    try:
        args = parse_args(__doc__)
        run(Path(__file__).resolve().parent, args.output, args.diagnostic_frame_count, args.dry_run)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"reproduce_external.py: {error}", file=sys.stderr)
        raise SystemExit(1)
