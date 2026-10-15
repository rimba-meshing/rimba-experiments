# RIMBA Experiments

This repository contains the scripts and tools to reproduce the RIMBA experiments
and generate results, tables, and figures.

## Repository structure

- `rimba/`: RIMBA library submodule.
- `reproduce.py`: experiment launcher.
- `tools/`: evaluation, analysis, and rendering tools.
- `results/`: generated measurements, meshes, and reports.

## Requirements

- Linux x86_64 and an NVIDIA GPU with a CUDA-compatible driver and NVML support.
- CUDA Toolkit with `nvcc` and CUDA C++20 support.
- A C++23 compiler with OpenMP support.
- CMake **4.2 or newer**, Make, Git, and GNU `time` at `/usr/bin/time`.
- Python **3.12** with NumPy, Matplotlib, Pillow, and Open3D CPU.
- Open3D runtime libraries: `libegl1`, `libgl1`, and `libgomp1` on Ubuntu.

Verified toolchain: Ubuntu 24.04, CUDA **13.2.0** (`nvcc 13.2.51`), GCC **13.3**,
and CMake **4.2.3**. Earlier CUDA releases have not been verified.

## Setup

Clone the repository and install the Python dependencies:

```bash
git clone --recurse-submodules https://github.com/rimba-meshing/rimba-experiments.git
cd rimba-experiments
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Quality evaluation

- Evaluator: [RuanJY/TanksAndTemples](https://github.com/RuanJY/TanksAndTemples).
- Use its `master` branch without local modifications.
- Python dependencies are included in the installation above.

```bash
git clone --branch master https://github.com/RuanJY/TanksAndTemples.git /path/to/TanksAndTemples
```

### Datasets

- **KITTI odometry:** sequence `07`, 1101 frames.
- **MaiCity:** sequence `01`, 100 frames.
- **Quality reference:** an independent point cloud accumulated from MaiCity
  sequence `02`, in the same global coordinate system.

Each dataset root must contain:

```text
sequences/<sequence>/
├── velodyne/000000.bin, 000001.bin, ...
├── poses.txt
└── calib.txt
```

Set the input paths:

```bash
export RI_KITTI_DATASET=/path/to/kitti/odometry/dataset
export RI_MAICITY_DATASET=/path/to/maicity/bin
export RI_MAICITY_GROUND_TRUTH=/path/to/maicity/bin/sequences/02/global.ply
export RI_TNT_RUNNER=/path/to/TanksAndTemples/python_toolbox/evaluation/run.py
```

## Run the experiments

```bash
python3 reproduce.py
```

The script builds RIMBA, runs the experiments, validates the results, and
writes tables and plots to `results/paper_protocol/<run>/report/README.md`.

- Variants: sequential, pre-scan, and pre-scan with the polyline blocker.
- Throughput: 3 warmups and 10 measured repetitions per variant.
- Memory, stage timings, and geometric quality are measured separately.
- Meshing times exclude dataset loading and PLY writing.
- Runtime and memory depend on hardware and load. Quality scores can vary
  slightly because the evaluator samples mesh points randomly.
- Comparisons with other methods require their own runs.

Useful options:

- `--skip-quality`: omit geometric-quality evaluation.
- `--diagnostic-frame-count 20`: run a short diagnostic interval.
- `--report-only PATH`: validate and summarize existing results.
- `--help`: show all launcher options.

The individual tools in `tools/` also provide `--help` for custom runs and
additional figures.

## Related repositories

- [RIMBA](https://github.com/rimba-meshing/rimba): algorithm and library.
- [RIMBA Meshing](https://github.com/rimba-meshing): project organization.

## Paper and citation

The RIMBA paper is in preparation.

- **Paper link:** to be added.
- **Citation:** BibTeX entry to be added after publication.

## License

[MIT License](LICENSE).
