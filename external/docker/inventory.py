"""Record the actual image packages without importing numerical libraries."""
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

NAMES = ("numpy", "open3d", "vdbfusion", "puma", "pybind11", "pyembree", "Click", "PyYAML", "easydict", "matplotlib", "pykitti", "tqdm", "trimesh", "scipy", "pandas", "Cython")
packages = {}
for name in NAMES:
    try:
        packages[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        pass
system = subprocess.check_output(["dpkg-query", "-W", "-f=${Package}=${Version}\n"], text=True)
record = {"python": sys.version, "machine": platform.machine(), "os_release": Path("/etc/os-release").read_text(),
          "packages": packages, "system_packages": system.splitlines(),
          "build": json.loads(Path("/opt/build-input.json").read_text())}
print(json.dumps(record, indent=2, sort_keys=True))
