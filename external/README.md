# External methods

This directory reproduces VDBFusion, PUMA, SLAMesh, ImMesh and CAD-Mesher with
the paper configurations and ground-truth poses. Each `source/` submodule pins
the method version used in the comparison.

## Requirements

- Linux x86_64, Python **3.10 or newer**, Git, and `tar`.
- Docker Engine, running and accessible to your user.
- Internet access for the first image build.
- The datasets described in the [main README](../README.md#datasets).

## Run the comparison

From the repository root, with the dataset roots configured:

```bash
python3 reproduce_external.py
python3 reproduce.py
```

The first command builds the method images on first use and reconstructs
MaiCity `01` and KITTI `03`, `05`, `06`, `07` and `10` with all five methods.
Later runs reuse the images. The second command evaluates the MaiCity meshes
against the same independent reference as RIMBA and includes the comparisons
in the report. Timing definitions follow the paper.

The launchers accept:

- `--diagnostic-frame-count N`: shorten each reconstructed sequence.
- `--output PATH`: choose a new output directory.
- `--dry-run`: check the setup and preview the commands without building or running.

Use the same frame count for both steps. External diagnostics need at least
three frames for initialization; five frames can be used for a short trial.

## Method environments

The images provide each method's compiler, Python packages and ROS dependencies.
The host only needs the requirements above. RIMBA's build and report generation
use the environment documented in the main README.

Tested on an Ubuntu 24.04 host with Docker Engine 29.7.2.

| Method | Upstream | Image environment | Main dependencies |
| --- | --- | --- | --- |
| VDBFusion | [PRBonn/vdbfusion](https://github.com/PRBonn/vdbfusion) | Ubuntu 22.04, Python 3.10 | NumPy 1.26.4, Open3D 0.19.0, VDBFusion 0.1.6 |
| PUMA | [PRBonn/puma](https://github.com/PRBonn/puma) | Ubuntu 20.04, Python 3.8 | NumPy 1.22.3, Open3D 0.15.2, Embree 2.17.7 |
| SLAMesh | [lab-sun/SLAMesh](https://github.com/lab-sun/SLAMesh) | Ubuntu 20.04, ROS Noetic | Ceres 2.1.0, PCL, LVR2, mesh_msgs |
| ImMesh | [hku-mars/ImMesh](https://github.com/hku-mars/ImMesh) | Ubuntu 20.04, ROS Noetic | CGAL, PCL, OpenCV, Livox driver |
| CAD-Mesher | [Yaepiii/CAD-Mesher](https://github.com/Yaepiii/CAD-Mesher) | Ubuntu 20.04, ROS Noetic | Ceres 1.14, PCL, LVR2, mesh_msgs |

Recipes are in `docker/`, with pinned base images and dependency revisions.
Method sources and patches are built into the images. Datasets are mounted
read-only, and output files are written as your user.

## Results

External meshes and execution records are saved in `.cache/external/` by default.
The latest completed campaign for each frame interval is selected automatically
by `reproduce.py`. It checks source revisions, image identities, input checksums
and reconstructed meshes before incorporating the results.

Build logs and image inventories also stay in `.cache/external/`. A failed
campaign keeps its diagnostic files and leaves the previous completed campaign
available. Changing a source pin or image recipe selects a new image.

The qualitative panel is composed from the reference captures in
[`assets/qualitative`](../assets/qualitative/README.md).
