"""Native command execution and environment selection."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import time


def execute(command: list[str], log: Path, cwd: Path | None = None, env: dict | None = None, timeout: int = 43200) -> float:
    log.parent.mkdir(parents=True, exist_ok=True)
    with (log.parent / "commands.txt").open("a") as stream:
        stream.write(shlex.join(command) + "\n")
    started = time.perf_counter()
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            interrupt(process)
            raise
    if code:
        raise RuntimeError(f"Command failed ({code}); see {log}")
    return time.perf_counter() - started


def interrupt(process):
    for sig, seconds in ((signal.SIGINT, 180), (signal.SIGTERM, 10), (signal.SIGKILL, 10)):
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=seconds)
            return
        except subprocess.TimeoutExpired:
            continue


def ros_environment(method: str) -> dict:
    variable = "RIMBA_" + method.upper() + "_SETUP"
    setup = Path(os.environ.get(variable, os.environ.get("RIMBA_ROS_SETUP", "/opt/ros/noetic/setup.bash"))).expanduser().resolve()
    if not setup.is_file():
        raise ValueError(f"Missing ROS environment: {setup}. Set {variable}; see external/README.md.")
    # Environment bytes are consumed internally and never written to logs.
    result = subprocess.run(["bash", "-c", 'set -e; source "$1" >&2; env -0', "rimba-ros", str(setup)], capture_output=True, check=True)
    environment = dict(os.environ)
    for item in result.stdout.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[os.fsdecode(key)] = os.fsdecode(value)
    cmake = Path(os.environ.get("RIMBA_ROS_CMAKE", "/usr/bin/cmake")).expanduser().resolve()
    if not cmake.is_file():
        raise ValueError("Set RIMBA_ROS_CMAKE to the CMake 3.x executable in the ROS environment")
    environment["PATH"] = str(cmake.parent) + os.pathsep + environment.get("PATH", "")
    return environment


def require_program(name: str, environment: dict | None = None) -> str:
    executable = shutil.which(name, path=(environment or os.environ).get("PATH"))
    if executable is None:
        raise ValueError(f"Required executable missing: {name}. See external/README.md.")
    return executable
