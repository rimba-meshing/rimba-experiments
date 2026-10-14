# Run from a clean Docker environment

Start from a clean clone of **this experiments repository**, with its pinned
source submodule initialized. The image installs dependencies only; it contains
no RIMBA binaries or local results. Compilation takes place from `rimba/` when
the protocol is launched.

Do not interpret successful image construction as a GPU runtime check. The
host GPU check below must succeed before launching CUDA builds with `native`
architecture detection or meshing measurements.

## Host and data setup

Use a Linux host with Docker, an NVIDIA driver, and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
The NVIDIA runtime must be registered with Docker as described in NVIDIA's
installation guide. Check GPU access with:

```bash
docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all \
  nvidia/cuda:13.2.0-devel-ubuntu24.04 nvidia-smi
```

On Docker with native CDI support, `--device=nvidia.com/gpu=all` is another
explicit NVIDIA selection. An unqualified `--gpus all` can select another
vendor on a host with multiple GPU vendors; use an explicit NVIDIA selection
for this CUDA workflow.
KITTI and MaiCity remain external read-only inputs. Their roots must have
`sequences/<sequence>/velodyne/*.bin`, `poses.txt`, and `calib.txt`. Quality
evaluation additionally uses MaiCity sequence 02's independent `global.ply`.

```bash
git clone --recurse-submodules https://github.com/rimba-meshing/rimba-experiments.git
cd rimba-experiments
export RI_KITTI_DATASET=/path/to/kitti/odometry/dataset
export RI_MAICITY_DATASET=/path/to/maicity/bin
docker build --pull --no-cache -t rimba-experiments:cuda13.2 \
  -f docker/Dockerfile docker
```

The default image includes the quality evaluator and figure dependencies. Use
`--target protocol` for orchestration alone, or `--target figures` for the
protocol and static renderers without Open3D.

## Full protocol

```bash
docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all --pid=host \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  --mount "type=bind,src=$RI_KITTI_DATASET,dst=/datasets/kitti,readonly" \
  --mount "type=bind,src=$RI_MAICITY_DATASET,dst=/datasets/maicity,readonly" \
  -e RI_KITTI_DATASET=/datasets/kitti \
  -e RI_MAICITY_DATASET=/datasets/maicity \
  -e RI_MAICITY_GROUND_TRUTH=/datasets/maicity/sequences/02/global.ply \
  rimba-experiments:cuda13.2 \
  python3 tools/run_paper_protocol.py --require-clean --keep-ablation-meshes \
  --build-jobs 2 --output results/paper_protocol/docker-full
```

Choose a new output directory for each run. For the first run, `rimba/build/`
must contain no builds copied from another environment. Subsequent processes
can reuse this container's builds. Do not mount a host virtual environment.
The documented invocation uses `--pid=host` so process IDs seen in `/proc`
and by NVML share the host namespace. This keeps process-VRAM attribution
independent of driver-specific PID translation inside an isolated namespace.
The dataset mounts are read-only and output files belong to the calling user.

For a diagnostic run, append `--kitti-frame-count 20 --maicity-frame-count 20`.
This exercises the protocol but does not reproduce a full-sequence experiment.
Append `--dry-run` to inspect commands. Use `--skip-quality` and omit the
ground-truth environment variable if the independent reference is unavailable.

## Dependency versions

The CUDA base image is pinned by digest in the Dockerfile. Ubuntu supplies
GCC/G++, Make, Python 3.12, Git, OpenMP, and GNU `time`. CMake is pinned to
4.2.3. Plotting uses NumPy 2.5.0, Matplotlib 3.11.0, and Pillow 12.3.0.
The image contains CUDA Toolkit 13.2.0, whose `nvcc --version` reports
`V13.2.51`. Toolkit release labels and the NVCC build number are recorded
separately; neither establishes compatibility with all earlier CUDA releases.
Quality uses `open3d-cpu==0.19.0` and the unmodified RuanJY evaluator at
`06f6537b471fd939eaed78678b3c0ebd22bd398a`. Its path is supplied by
`RI_TNT_RUNNER` inside the image. CPU Open3D evaluates the geometry; RIMBA's
meshing executable still uses CUDA.

The evaluator's legacy `requirements.txt` specifies Open3D 0.9. Use the
requirements supplied here for this Python 3.12 environment. Do not install
that legacy requirements file over the container environment.
`requirements.lock.txt` also constrains the transitive plotting and quality
packages to the recorded environment. Ubuntu package revisions and the host
driver should be captured with the run's machine metadata.

The driver and GPU belong to the host. Runtime and memory measurements depend
on that hardware and its load. Geometry comparisons must use the same source,
inputs, poses, and flags. The evaluator samples mesh points randomly, so its
precision/recall/F1 can vary slightly between runs.

For figures, keep the same mounts and replace the container command with the
commands in [../protocols/figures.md](../protocols/figures.md).
The same image can check a completed bundle with `tools/check_protocol.py`;
see [../REPRODUCIBILITY.md](../REPRODUCIBILITY.md#check-the-result-bundle).
