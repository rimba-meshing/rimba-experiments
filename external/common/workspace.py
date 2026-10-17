"""Use the patched ROS workspace compiled into the selected image."""
import json
import os
from pathlib import Path
import subprocess

from .case import write_json
from .process import ros_environment


def build(case):
    prepared = os.environ.get("RIMBA_EXTERNAL_WORKSPACE")
    if not prepared:
        raise ValueError("Run ROS methods through reproduce_external.py")
    record = json.loads(Path("/opt/build-record.json").read_text())
    if record["source_commit"] != case.revisions["source_commit"]:
        raise ValueError("Compiled image source differs from the requested submodule")
    write_json(case.output / "build.json", record)
    return Path(prepared)


def built_environment(case, workspace):
    environment = ros_environment(case.method)
    command = ["bash", "-c", 'set -e; source "$1" >&2; env -0', "rimba-workspace", str(workspace / "devel/setup.bash")]
    result = subprocess.run(command, env=environment, capture_output=True, check=True)
    for item in result.stdout.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[os.fsdecode(key)] = os.fsdecode(value)
    return environment
