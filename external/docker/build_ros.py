"""Build the pinned ROS dependencies and patched external method once."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

WORKSPACE = Path("/opt/workspace")
RELEASE = ["-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g0"]
PATCHES = {
    "slamesh": (("0001-portable-catkin-dir.patch", 1), ("0002-sequence-pose-mapping.patch", 1)),
    "immesh": (("0001-enable-headless-autosave.patch", 0), ("0002-sequence-pose-mapping.patch", 1), ("0003-output-directory.patch", 1)),
    "cad_mesher": (),
}


def run(command, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def checkout(url, revision, destination):
    run(["git", "clone", "--no-checkout", url, str(destination)])
    run(["git", "checkout", "--detach", revision], destination)


def cmake(source, flags=()):
    directory = source / "build"
    run(["cmake", "-S", str(source), "-B", str(directory), *RELEASE, *flags])
    run(["cmake", "--build", str(directory), "-j2"])
    run(["cmake", "--install", str(directory)])


def dependencies(method):
    if method == "slamesh":
        source = Path("/opt/ceres")
        checkout("https://github.com/ceres-solver/ceres-solver.git", "f68321e7de8929fbcdb95dd42877531e64f72f66", source)
        cmake(source, ["-DBUILD_TESTING=OFF", "-DBUILD_EXAMPLES=OFF", "-DBUILD_BENCHMARKS=OFF", "-DBUILD_SHARED_LIBS=ON"])
        shutil.rmtree(source)
    elif method == "immesh":
        source = Path("/opt/livox-sdk")
        checkout("https://github.com/Livox-SDK/Livox-SDK.git", "9306596a2bf15c1343bc023b497465ed0a32909d", source)
        cmake(source)
        shutil.rmtree(source)
        checkout("https://github.com/Livox-SDK/livox_ros_driver.git", "3d240d5666129e1a3052e78ee8487a04b08fdda3", WORKSPACE / "src/livox_ros_driver")
    run(["ldconfig"])


def method_build(method):
    source = Path("/opt/source/CAD_Mesher") if method == "cad_mesher" else Path("/opt/source")
    target = WORKSPACE / "src" / ("ImMesh" if method == "immesh" else method)
    shutil.copytree(source, target)
    for name, strip in PATCHES[method]:
        run(["patch", f"-p{strip}", "--batch", "-i", "/opt/patches/" + name], target)
    command = 'source /opt/ros/noetic/setup.bash && catkin_make -j1 -DCMAKE_BUILD_TYPE=Release "-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g0"'
    run(["bash", "-c", command], WORKSPACE)
    record = json.loads(Path("/opt/build-input.json").read_text())
    record["compiler"] = subprocess.check_output(["c++", "--version"], text=True).splitlines()[0]
    record["cmake"] = subprocess.check_output(["cmake", "--version"], text=True).splitlines()[0]
    record["binary_sha256"] = {}
    import hashlib
    package = "ImMesh" if method == "immesh" else method
    for path in (WORKSPACE / "devel/lib" / package).glob("*"):
        if path.is_file():
            record["binary_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    Path("/opt/build-record.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "dependencies":
        dependencies(sys.argv[2])
    else:
        method_build(sys.argv[2])
