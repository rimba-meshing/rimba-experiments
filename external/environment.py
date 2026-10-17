"""Host prerequisites for Docker-based external reconstruction."""
import os
import platform
from pathlib import Path
import subprocess

from .common.case import METHODS, git
from .common.process import require_program


def preflight(root):
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Commit/stash checkout changes before measuring external methods")
    for program in ("docker", "git", "tar"):
        require_program(program)
    try:
        version = subprocess.check_output(["docker", "version", "--format", "{{.Server.Version}}"], text=True, stderr=subprocess.STDOUT).strip()
        architecture = subprocess.check_output(["docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"], text=True).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("Docker Engine must be running and accessible to the current user") from error
    if architecture not in {"linux/x86_64", "linux/amd64"}:
        raise ValueError("The external method images require a Linux x86_64 Docker engine")
    for method in METHODS:
        source = root / "external" / method / "source"
        committed = git(root, "rev-parse", "HEAD:external/" + method + "/source")
        if not (source / ".git").is_file() or git(source, "rev-parse", "HEAD") != committed or git(source, "status", "--porcelain"):
            raise ValueError(f"Initialize the clean pinned {method} submodule: git submodule update --init --recursive")
    return {"docker_version": version, "architecture": architecture, "hardware": hardware()}


def hardware():
    cpu = platform.processor()
    path = Path("/proc/cpuinfo")
    if path.is_file():
        cpu = next((line.split(":", 1)[1].strip() for line in path.read_text().splitlines() if line.startswith("model name")), cpu)
    return {"cpu": cpu, "machine": platform.machine(), "platform": platform.platform(), "logical_cpus": os.cpu_count()}
