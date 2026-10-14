# Reproducibility

Prepare the environment and inputs below, then run `python3 reproduce.py`
from this repository. The script compiles RIMBA, runs its measurements,
validates the artifacts, and generates a report. The protocol runs on a
Linux workstation and does not require an HPC system or a separate Python
implementation of the meshing method.

## Pinned source

The `rimba/` Git submodule records the exact RIMBA commit associated with this
experiment revision. Initialize it with `git clone --recurse-submodules` or:

```bash
git submodule update --init --recursive
```

Keep the source pin unchanged for reproduction. Measurement runs require
clean source and experiments checkouts, and record both commits and commands.

## Requirements

### System toolchain

- Linux x86_64 with an NVIDIA GPU and a compatible NVIDIA driver.
- CUDA Toolkit with `nvcc` and CUDA C++20 support.
- A C++23-compatible host compiler supported by the installed CUDA Toolkit;
  OpenMP support is required for the paper's CPU/CUDA configurations.
- CMake **4.2 or newer**, Make, Git, and GNU `time` at `/usr/bin/time`.
- Python **3.10 or newer** for orchestration. The pinned full analysis and
  evaluation environment below was verified on **Python 3.12**.
- NVIDIA's NVML library for process-VRAM sampling (`nvidia-smi` must work).
- EGL, GL, and OpenMP runtime libraries for the Open3D CPU wheel. On Ubuntu
  these are provided by `libegl1`, `libgl1`, and `libgomp1`.

Verified combination: Ubuntu 24.04 x86_64, GCC 13.3.0, CUDA Toolkit
**13.2.0** (`nvcc V13.2.51`), CMake **4.2.3**, Python **3.12.3**, NVIDIA
RTX 4060 Laptop, and driver **595.91.07**. This records one working
combination; earlier CUDA versions and other toolchain/GPU combinations have
not been verified. See NVIDIA's [CUDA 13.2 Linux installation
guide](https://docs.nvidia.com/cuda/archive/13.2.0/cuda-installation-guide-linux/index.html)
for its supported host compilers and platforms.

### Python packages

Use an environment with the pinned plotting and quality dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -c requirements.lock.txt
```

Direct versions are CMake 4.2.3, NumPy 2.5.0, Matplotlib 3.11.0,
Pillow 12.3.0, and `open3d-cpu` 0.19.0. The lock file constrains transitive
packages for the verified Python 3.12 environment. GNU tools, CUDA, the
compiler, and the driver must already be installed; pip does not provide them.
The orchestration and integrity checker use the Python standard library;
the automatic plots use the figure packages. Without quality evaluation,
install `requirements-figures.txt` and supply CMake separately.

### Quality evaluator

The complete launcher requires the [RuanJY TanksAndTemples
fork](https://github.com/RuanJY/TanksAndTemples) at the fixed revision below:

```bash
git clone https://github.com/RuanJY/TanksAndTemples.git /path/to/TanksAndTemples
git -C /path/to/TanksAndTemples checkout --detach 06f6537b471fd939eaed78678b3c0ebd22bd398a
export RI_TNT_RUNNER=/path/to/TanksAndTemples/python_toolbox/evaluation/run.py
```

Keep that checkout unmodified. Use this repository's quality dependencies:
the fork's legacy requirements specify Open3D 0.9, which is not the verified
Python 3.12 setup. The wrapper invokes the fork's no-registration evaluation
directly, with τ = 0.10 m, 6,553,600 mesh samples, and 0.05 m voxel size.
Open3D CPU evaluates geometry; the meshing executable uses CUDA.

## Dataset paths

Download KITTI odometry and MaiCity separately. The full protocol uses KITTI
sequence `07`, frames `0–1100`, and MaiCity sequence `01`, frames `0–99`.
Each root must contain:

```text
sequences/<sequence>/
├── velodyne/000000.bin, 000001.bin, ...
├── poses.txt
└── calib.txt
```

Supply the roots and an **independent** MaiCity reference point cloud,
normally accumulated from sequence `02`:

```bash
export RI_KITTI_DATASET=/path/to/kitti/odometry/dataset
export RI_MAICITY_DATASET=/path/to/maicity/bin
export RI_MAICITY_GROUND_TRUTH=/path/to/maicity/bin/sequences/02/global.ply
```

The launcher also checks `sequences/02/global.ply` under the MaiCity root if
`RI_MAICITY_GROUND_TRUTH` is unset. Dataset paths can instead be supplied with
`--kitti-dataset`, `--maicity-dataset`, and `--quality-ground-truth`.
Inputs are read from their existing locations; they are not copied or downloaded.

## Run with one command

From the repository root, with the prepared Python environment active:

```bash
python3 reproduce.py
```

The launcher:

1. Checks input files, tool availability, clean revisions, and evaluator setup.
2. Configures and builds three native-architecture CUDA configurations.
3. Runs throughput, scheduler ablations, separate memory passes, stage timings,
   and three MaiCity quality evaluations.
4. Checks all 18 sections, 60 raw throughput samples, derived statistics,
   complete frame intervals, memory traces, and quality sidecars.
5. Writes readable tables and PNG/PDF throughput, memory, and quality plots
   in `report/`, together with `report/verification.json`.

Throughput uses **3 warmups and 10 measured repetitions per variant**.
Use the GPU with unrelated workloads stopped when collecting results for
comparison. Runtime and memory depend on hardware, driver, and load; random
mesh sampling can produce small precision/recall/F1 differences. The script
covers the RIMBA configurations; comparisons against external methods require
those methods' reconstructions and measurements.

Output defaults to a fresh timestamped `results/paper_protocol/full_*/`
directory. Use `--output PATH` to select a new directory under `results/` or
outside the checkout, and `--build-jobs N` to control compilation parallelism.
Existing directories are refused.
Builds remain under `rimba/build/`; start without build caches from another
machine or toolchain. Allow disk space for six full-sequence PLY meshes and
quality artifacts. A verified full run took about 86 minutes on the GPU above;
this is an observed duration, not a runtime guarantee.

Useful variants:

```bash
# Validate prerequisites and inspect commands without running or writing files.
python3 reproduce.py --dry-run
# Meshing measurements and reports without geometric quality.
python3 reproduce.py --skip-quality
# Short diagnostic interval, explicitly labelled in its report.
python3 reproduce.py --diagnostic-frame-count 20 --skip-quality
# Check and report a complete existing bundle without running measurements.
python3 reproduce.py --report-only results/paper_protocol/my-run
```

For a short bundle, pass its `--diagnostic-frame-count` to `--report-only`.
If quality was omitted, also pass `--skip-quality`. Repetition counts remain
the standard 3 warmups and 10 measured runs in this launcher.

## Outputs and advanced use

Each bundle contains `metadata.json`, `environment.json`, the launch command,
individual build/run commands and logs, six meshes, raw timings and derived
CSV tables. Quality outputs include evaluation meshes and precision/recall
curves. Method illustrations have separate capture/render commands in
[protocols/figures.md](protocols/figures.md).

`tools/run_paper_protocol.py` exposes advanced frame ranges, repetition counts,
and individual protocol sections. See its `--help` and
[protocols/paper_protocol.md](protocols/paper_protocol.md) for definitions and
measurement boundaries. Check advanced runs explicitly:

```bash
python3 tools/check_protocol.py results/paper_protocol/my-run \
  --expected-kitti-frames 1101 --expected-maicity-frames 100 \
  --output results/paper_protocol/my-run/report/verification.json
python3 tools/report_protocol.py results/paper_protocol/my-run
```

Use the actual frame counts for short intervals, `--skip-quality` if omitted,
and explicit `--expected-warmups` / `--expected-runs` for different repetitions.
`results/` and `.venv/` are ignored by Git. Archive completed bundles separately;
only reviewed publication artifacts should be added deliberately to a release.
