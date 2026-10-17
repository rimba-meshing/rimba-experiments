#!/usr/bin/env python3
"""Reproduce the RIMBA paper tables and figures in a prepared environment."""
import importlib.metadata
from pathlib import Path
import subprocess
import sys

from tools.reproduction.campaign import run


if __name__ == "__main__":
    try:
        if sys.argv[1:]:
            raise ValueError("Run python3 reproduce.py without arguments; see README.md for dataset setup.")
        run(Path(__file__).resolve().parent)
    except (OSError, ValueError, subprocess.CalledProcessError, importlib.metadata.PackageNotFoundError) as error:
        print(f"reproduce.py: {error}", file=sys.stderr)
        raise SystemExit(1)
