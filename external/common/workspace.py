"""Build patched workspace copies, leaving the pinned submodules untouched."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

from .case import git, sha256, write_json
from .process import execute, ros_environment

PATCHES = {
    "slamesh": (("0001-portable-catkin-dir.patch", 1), ("0002-sequence-pose-mapping.patch", 1)),
    "immesh": (("0001-enable-headless-autosave.patch", 0), ("0002-sequence-pose-mapping.patch", 1), ("0003-output-directory.patch", 1)),
    "cad_mesher": (),
}


def fingerprint(case, environment):
    setup = Path(os.environ.get("RIMBA_" + case.method.upper() + "_SETUP", os.environ.get("RIMBA_ROS_SETUP", "/opt/ros/noetic/setup.bash"))).expanduser().resolve()
    patches = {name: sha256(case.root / "external/patches" / case.method / name) for name, _ in PATCHES[case.method]}
    compiler = subprocess.check_output(["c++", "--version"], env=environment, text=True).splitlines()[0]
    cmake = subprocess.check_output(["cmake", "--version"], env=environment, text=True).splitlines()[0]
    record = {"source": git(case.source, "rev-parse", "HEAD"), "patches": patches,
              "setup": str(setup.resolve()), "setup_sha256": sha256(setup),
              "prefix": environment.get("CMAKE_PREFIX_PATH", ""), "compiler": compiler, "cmake": cmake}
    key = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:20]
    return key, record


def build(case):
    environment = ros_environment(case.method)
    key, record = fingerprint(case, environment)
    workspace = case.root / ".cache/external/build" / (case.method + "-" + key)
    ready = workspace / "ready.json"
    if not ready.is_file():
        if workspace.exists():
            raise ValueError(f"Incomplete build at {workspace}; inspect/remove it before retrying")
        source = case.source / "CAD_Mesher" if case.method == "cad_mesher" else case.source
        package = workspace / "src" / ("ImMesh" if case.method == "immesh" else case.method)
        shutil.copytree(source, package, ignore=shutil.ignore_patterns(".git", "build", "devel", "__pycache__"))
        for name, strip in PATCHES[case.method]:
            patch = case.root / "external/patches" / case.method / name
            execute(["patch", f"-p{strip}", "--batch", "--forward", "-i", str(patch)], workspace / (name + ".log"), package)
        execute(["catkin_make", "-DCMAKE_BUILD_TYPE=Release", "-j2"], workspace / "build.log", workspace, environment)
        if not (workspace / "devel/setup.bash").is_file():
            raise ValueError(f"Missing catkin build output: {workspace}")
        write_json(ready, record)
    write_json(case.output / "build.json", record)
    return workspace


def built_environment(case, workspace):
    environment = ros_environment(case.method)
    command = ["bash", "-c", 'set -e; source "$1" >&2; env -0', "rimba-workspace", str(workspace / "devel/setup.bash")]
    result = subprocess.run(command, env=environment, capture_output=True, check=True)
    for item in result.stdout.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[os.fsdecode(key)] = os.fsdecode(value)
    return environment
