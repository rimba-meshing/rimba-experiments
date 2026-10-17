"""Prerequisites and acquisition of the paper's quality evaluator."""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from ..paper_results.latex import require_rendering

EVALUATOR_URL = "https://github.com/RuanJY/TanksAndTemples.git"


def capture(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError(f"Prerequisite command failed: {shlex.join(command)}\n{error.output}") from error


def preflight(root: Path) -> dict:
    require_rendering()
    source = root / "rimba"
    if not (source / "CMakeLists.txt").is_file():
        raise ValueError("Initialize the source with git submodule update --init --recursive.")
    compiler = os.environ.get("CXX", "c++")
    for executable in ("git", "cmake", "nvcc", "nvidia-smi", "make", compiler):
        if shutil.which(executable) is None:
            raise ValueError(f"Required executable not found: {executable}")
    version = capture(["cmake", "--version"])
    match = re.search(r"cmake version (\d+)\.(\d+)", version)
    if match is None or tuple(map(int, match.groups())) < (4, 2):
        raise ValueError("CMake 4.2 or newer is required.")
    if not Path("/usr/bin/time").is_file() or "GNU" not in capture(["/usr/bin/time", "--version"]):
        raise ValueError("GNU time at /usr/bin/time is required for CPU peak-memory measurements.")
    for repo in (root, source):
        if capture(["git", "-C", str(repo), "status", "--porcelain"]):
            raise ValueError(f"Commit or discard changes before reproduction: {repo}")
    packages = {"numpy": "numpy", "matplotlib": "matplotlib", "Pillow": "PIL", "open3d-cpu": "open3d"}
    # Imports stay out of the orchestration process to avoid persistent worker pools.
    capture([sys.executable, "-c", "; ".join(f"import {module}" for module in packages.values())])
    return {
        "python": sys.version, "cmake": version, "nvcc": capture(["nvcc", "--version"]),
        "host_compiler": capture([compiler, "--version"]),
        "gpu": capture(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        "packages": {name: importlib.metadata.version(name) for name in packages},
    }


def evaluator(root: Path) -> Path:
    checkout = root / ".cache/TanksAndTemples"
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        print("Downloading the TanksAndTemples master evaluator (first run only).", flush=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", "master", EVALUATOR_URL, str(checkout)], check=True)
    # Read the stored URL; `remote get-url` applies user-specific SSH rewrites.
    if capture(["git", "-C", str(checkout), "config", "--get", "remote.origin.url"]) != EVALUATOR_URL:
        raise ValueError(f"Unexpected evaluator origin: {checkout}")
    if capture(["git", "-C", str(checkout), "branch", "--show-current"]) != "master":
        raise ValueError("The cached evaluator must be on master.")
    if capture(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("The cached evaluator has tracked modifications.")
    runner = checkout / "python_toolbox/evaluation/run.py"
    if not runner.is_file():
        raise ValueError(f"Missing quality evaluator: {runner}")
    return runner
