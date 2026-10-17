# External methods

This directory reproduces VDBFusion, PUMA, SLAMesh, ImMesh and CAD-Mesher with
the paper configurations and ground-truth poses. Each `source/` is a Git
submodule pinned to the version used in the comparison. The accompanying
runners, configurations and patches adapt those versions to the shared datasets.

## Prepare the environments

The versions below come from our retained external-method environments.
Each method's operating system belongs to its execution environment and can
differ from the host system and from the RIMBA environment.

Use Python **3.10 or newer** for the campaign launcher. Each method uses its own
environment. The root `requirements.txt` remains the environment for RIMBA,
evaluation and reporting.

### VDBFusion

- Native Python environment: Python **3.10.19**, NumPy **1.26.4**,
  Open3D **0.19.0**, VDBFusion **0.1.6**.
- A C++ compiler, Make, CMake **3.x**, and the Open3D runtime libraries listed
  in the main README. VDBFusion downloads its C++ build dependencies.

From the repository root:

```bash
python3.10 -m venv external/vdbfusion/.venv
external/vdbfusion/.venv/bin/python -m pip install -r external/vdbfusion/requirements.txt
external/vdbfusion/.venv/bin/python -m pip install --no-build-isolation --no-deps ./external/vdbfusion/source
```

### PUMA

- Ubuntu **20.04.4** execution environment, GCC **9.4.0** with OpenMP.
- Python **3.8.10**, NumPy **1.22.3**, Open3D **0.15.2**, PUMA **0.1**.
- Embree **2.17.7** and `pyembree` **0.1.6**, as described in
  [PUMA's installation guide](puma/source/INSTALL.md).

The Python requirements use the versions installed in our retained environment.

```bash
python3.8 -m venv external/puma/.venv
external/puma/.venv/bin/python -m pip install -r external/puma/requirements.txt
external/puma/.venv/bin/python -m pip install --no-build-isolation --no-deps ./external/puma/source
```

PUMA's incremental mapper is used directly. The runner converts the scans to PLY
and compensates PUMA's fixed KITTI pose conversion for MaiCity.

### SLAMesh, ImMesh and CAD-Mesher

Our retained ROS environments use:

- Ubuntu **20.04.6** and ROS **Noetic**.
- Python **3.8.10** and NumPy **1.17.4**.
- GCC **9.4.0**, CMake **3.16.3**, and catkin **0.8.12**.
- PCL **1.10.0**, Eigen **3.3.7**, and OpenCV **4.2.0**.
- Make, `patch`, `rospy`, `tf`, `tf2_ros`, `sensor_msgs`, and `nav_msgs`.

| Method | Additional dependencies in our environment | Source instructions |
| --- | --- | --- |
| SLAMesh | Ceres **2.1.0**, Boost, LVR2 ROS package **20.11.3**, `mesh_msgs` and `mesh_msgs_conversions` **1.1.0** | [SLAMesh](slamesh/source/README.md#2-build) |
| ImMesh | Ceres **1.14.0**, CGAL **5.0.2**, TBB **2020.1**, GLEW, GLFW, GLM, OpenGL/GLU, `cv_bridge`, `eigen_conversions`, `message_filters`, `rosbag`, Livox driver | [ImMesh](immesh/source/README.md) |
| CAD-Mesher | Ceres **1.14.0**, Boost, LVR2 ROS package **20.11.3**, `mesh_msgs` and `mesh_msgs_conversions` **1.1.0** | [CAD-Mesher](cad_mesher/source/CAD_Mesher/README.md#2-build) |

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

The migrated native launchers still need an end-to-end check in these environments.

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
[`assets/qualitative`](../assets/qualitative/README.md).
