"""Run a reconstruction in its image with read-only source and dataset mounts."""
import os
import subprocess
import uuid

from .common.process import execute


def mount(path, readonly=True):
    text = str(path)
    if "," in text:
        raise ValueError("Docker mount paths must not contain commas")
    return "type=bind,src=" + text + ",dst=" + text + (",readonly" if readonly else "")


def command(case, request, image, name, inputs=None):
    command = ["docker", "run", "--rm", "--init", "--name", name, "--network", "none",
               "--user", f"{os.getuid()}:{os.getgid()}", "--workdir", str(case.root),
               "--mount", mount(case.root), "--mount", mount(case.output.parents[2], False)]
    paths = {path.resolve() for path in (inputs if inputs is not None else case.workload.directory.iterdir())}
    for path in sorted(paths):
        command += ["--mount", mount(path)]
    command += ["--entrypoint", "python3", image["image_id"], "-m", "external." + case.method + ".run", str(request)]
    return command


def run(case, request, image):
    name = "rimba-external-" + uuid.uuid4().hex[:16]
    try:
        execute(command(case, request, image, name), case.output / "runner.log", case.root)
    finally:
        # Only this case's uniquely named container is eligible for cleanup.
        subprocess.run(["docker", "rm", "--force", name], capture_output=True)
