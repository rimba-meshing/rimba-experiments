# External methods

This directory reproduces VDBFusion, PUMA, SLAMesh, ImMesh and CAD-Mesher with
the paper configurations and ground-truth poses. Each `source/` is a Git
submodule pinned to the version used in the comparison. The accompanying
runners, configurations and patches adapt those versions to the shared datasets.

## Prepare the environments

Use Python **3.10 or newer** for the campaign launcher. Each method uses its own
environment. The root `requirements.txt` remains the environment for RIMBA,
evaluation and reporting.

### VDBFusion

- Python **3.10**, NumPy **1.26.4**, Open3D **0.19.0**.
- A C++ compiler, Make, CMake **3.x**, and the Open3D runtime libraries listed
  in the main README. VDBFusion downloads its C++ build dependencies.

From the repository root:

```bash
python3.10 -m venv external/vdbfusion/.venv
external/vdbfusion/.venv/bin/python -m pip install -r external/vdbfusion/requirements.txt
external/vdbfusion/.venv/bin/python -m pip install --no-build-isolation --no-deps ./external/vdbfusion/source
```

### PUMA

- Ubuntu **20.04**, Python **3.8**, NumPy **1.24.4**, Open3D **0.15.2**.
- A C++ compiler with OpenMP and the build dependencies described in
  [PUMA's installation guide](puma/source/INSTALL.md).
- Embree **2.17.7** and its `pyembree` **0.1.6** bindings if required by the
  installed PUMA components. Embree 3 is not interchangeable with this version.

```bash
python3.8 -m venv external/puma/.venv
external/puma/.venv/bin/python -m pip install -r external/puma/requirements.txt
external/puma/.venv/bin/python -m pip install --no-build-isolation --no-deps ./external/puma/source
```

PUMA's incremental mapper is used directly. The runner converts the scans to PLY
and compensates PUMA's fixed KITTI pose conversion for MaiCity.

### SLAMesh, ImMesh and CAD-Mesher

Prepare ROS **Noetic** environments on Ubuntu **20.04**, with catkin, GCC/G++,
Make, `patch` and CMake **3.x**. Use the ROS Python **3.8** interpreter with
NumPy, `rospy`, `tf`, `tf2_ros`, `sensor_msgs` and `nav_msgs`.

| Method | Additional dependencies | Source instructions |
| --- | --- | --- |
| SLAMesh | Ceres **2.1.0**, PCL, Eigen, Boost, LVR2 **2.x**, `mesh_msgs`, `mesh_msgs_conversions` | [SLAMesh](slamesh/source/README.md#2-build) |
| ImMesh | PCL, Eigen, OpenCV, CGAL, TBB, GLEW, GLFW, GLM, OpenGL/GLU, `cv_bridge`, `eigen_conversions`, `message_filters`, `rosbag`, Livox driver | [ImMesh](immesh/source/README.md) |
| CAD-Mesher | Ceres **1.14** (Ubuntu 20.04), PCL, Eigen, OpenCV, Boost, LVR2 **2.x**, `mesh_msgs`, `mesh_msgs_conversions` | [CAD-Mesher](cad_mesher/source/CAD_Mesher/README.md#2-build) |

The ROS packages `ros-noetic-lvr2`, `ros-noetic-mesh-msgs` and
`ros-noetic-mesh-msgs-conversions` provide the mesh dependencies. For ImMesh,
build [livox_ros_driver](https://github.com/Livox-SDK/livox_ros_driver) at
`3d240d5666129e1a3052e78ee8487a04b08fdda3` in a dependency workspace and source
its `devel/setup.bash`.

The default ROS setup is `/opt/ros/noetic/setup.bash`. If dependencies are in
separate workspaces or prefixes, provide a setup script for each method:

```bash
export RIMBA_SLAMESH_SETUP=/path/to/slamesh-dependencies/setup.bash
export RIMBA_IMMESH_SETUP=/path/to/immesh-dependencies/devel/setup.bash
export RIMBA_CAD_MESHER_SETUP=/path/to/cad-dependencies/setup.bash
```

Each setup script must source ROS and expose that method's dependencies,
including its Ceres library. `RIMBA_ROS_SETUP` selects a shared setup when suitable.
`RIMBA_ROS_CMAKE` selects the ROS CMake executable (default `/usr/bin/cmake`),
and `RIMBA_ROS_PYTHON` selects the ROS Python (default `/usr/bin/python3`).
The launcher builds the method workspaces automatically in `.cache/external/`
and starts a private ROS master for each reconstruction.

For an existing Python environment, set `RIMBA_VDBFUSION_PYTHON` or
`RIMBA_PUMA_PYTHON` to its interpreter. The package must be installed from this
checkout's pinned `source/`. ROS replay interpreters can also be selected with
`RIMBA_IMMESH_PYTHON` and `RIMBA_CAD_MESHER_PYTHON`.

These native adapters have not yet been validated together in fresh prepared
environments. The system dependencies follow the previous execution paths; the accompanying
Python requirements still need validation with these adapters. They are separate
from the verified RIMBA toolchain.

## Run the comparison

Set the dataset roots as described in the main README, then run:

```bash
python3 reproduce_external.py
python3 reproduce.py
```

The first command reconstructs MaiCity `01` and KITTI `03`, `05`, `06`, `07` and
`10` with all five methods. The second evaluates their MaiCity meshes against
the same independent reference as RIMBA and assembles the tables and figures.
Timing definitions follow the paper.

Both launchers accept `--diagnostic-frame-count`, `--output` and `--dry-run`.
Use the same frame count for both steps; external diagnostics need at least
three frames for initialization. Outputs must be new directories.

External meshes and execution records stay in `.cache/external/` by default.
The latest completed full or diagnostic campaign is selected automatically.
An incomplete campaign never replaces the previous completed one. The main
launcher checks the source revisions, input checksums and reconstructed meshes
before reuse. Rebuild a changed environment in a new checkout, or remove its
cached workspace before rebuilding.

The qualitative panel is composed from the reference captures in
[`assets/qualitative`](../assets/qualitative/README.md). Its original camera
matrices were not saved, so it is not re-rendered from new meshes.

## Adaptations and licenses

- VDBFusion: fixed-pose integration and final mesh extraction.
- PUMA: fixed-pose incremental mapping and its existing timing CSV support.
- SLAMesh: portable catkin lookup and sequence-pose mapping patches.
- ImMesh: headless export, sequence poses and a per-run output directory.
  MaiCity quality uses the original pose-index correction derived from the
  first two LiDAR poses.
- CAD-Mesher: the pinned fork's per-scan acknowledgement replay.

Patches are applied to build copies. Source submodules remain unchanged.
Each external project retains its own license and citation instructions;
the repository's MIT license covers the accompanying reproduction tools.
