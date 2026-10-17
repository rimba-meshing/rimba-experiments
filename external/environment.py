"""Prerequisite checks for the separate external-method environments."""
import json
import os
from pathlib import Path
import platform
import subprocess

from .common.case import METHODS, git
from .common.process import python_for, require_program, ros_environment


def python_probe(root, method):
    python = python_for(root, method)
    modules = ["numpy", "open3d", "vdbfusion"] if method == "vdbfusion" else ["numpy", "open3d", "puma", "yaml", "click", "easydict", "pykitti", "trimesh", "tqdm"]
    code = ("import importlib, importlib.metadata as m, json, sys; "
            "modules=[importlib.import_module(name) for name in json.loads(sys.argv[1])]; "
            "d=m.distribution(sys.argv[2]); "
            "print(json.dumps({'python':sys.version,'modules':{x.__name__:getattr(x,'__version__','unknown') for x in modules},"
            "'installation':json.loads(d.read_text('direct_url.json') or '{}')}))")
    result = subprocess.run([python, "-c", code, json.dumps(modules), method], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"{method} environment is not ready ({python}): {result.stderr.strip()}. See external/README.md.")
    record = json.loads(result.stdout.strip().splitlines()[-1])
    from urllib.parse import unquote, urlparse
    location = urlparse(record["installation"].get("url", ""))
    expected = (root / "external" / method / "source").resolve()
    if location.scheme != "file" or Path(unquote(location.path)).resolve() != expected:
        raise ValueError(f"Install {method} from its pinned external/{method}/source checkout; see external/README.md.")
    return {"executable": python, **record}


def ros_probe(method):
    environment = ros_environment(method)
    for command in ("roscore", "rosrun", "rosparam", "rospack", "catkin_make", "patch", "c++", "make"):
        require_program(command, environment)
    cmake = subprocess.check_output(["cmake", "--version"], env=environment, text=True).splitlines()[0]
    if not cmake.startswith("cmake version 3."):
        raise ValueError("The legacy catkin methods require CMake 3.x; set RIMBA_ROS_CMAKE")
    packages = ["pcl_ros", "tf", "nav_msgs", "sensor_msgs"]
    if method == "immesh":
        packages += ["livox_ros_driver", "cv_bridge"]
        require_program("rosbag", environment)
    else:
        packages += ["mesh_msgs"]
    for package in packages:
        subprocess.run(["rospack", "find", package], env=environment, capture_output=True, check=True)
    python = os.environ.get("RIMBA_" + method.upper() + "_PYTHON", os.environ.get("RIMBA_ROS_PYTHON", "/usr/bin/python3"))
    imports = "import numpy, rospy, tf, tf2_ros, sensor_msgs, nav_msgs" + (", rosbag" if method == "immesh" else "")
    version = subprocess.check_output([python, "-c", imports + "; import sys; print(sys.version)"], env=environment, text=True).strip()
    return {"python": python, "python_version": version, "ros_distro": environment.get("ROS_DISTRO"), "cmake": cmake}


def preflight(root):
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Commit/stash checkout changes before measuring external methods")
    records = {}
    for method in METHODS:
        source = root / "external" / method / "source"
        committed = git(root, "rev-parse", "HEAD:external/" + method + "/source")
        if not (source / ".git").is_file() or git(source, "rev-parse", "HEAD") != committed or git(source, "status", "--porcelain"):
            raise ValueError(f"Initialize the clean pinned {method} submodule: git submodule update --init --recursive")
        records[method] = python_probe(root, method) if method in {"vdbfusion", "puma"} else ros_probe(method)
    return {"methods": records, "hardware": hardware()}


def hardware():
    cpu = platform.processor()
    path = Path("/proc/cpuinfo")
    if path.is_file():
        cpu = next((line.split(":", 1)[1].strip() for line in path.read_text().splitlines() if line.startswith("model name")), cpu)
    return {"cpu": cpu, "machine": platform.machine(), "platform": platform.platform(), "logical_cpus": os.cpu_count()}
