#!/usr/bin/env python3
"""Export the paper's tables and figures from a measurement bundle."""
import subprocess
import sys

from paper_results.export import main

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        print(f"report_protocol.py: {error}", file=sys.stderr)
        raise SystemExit(1)
