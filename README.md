# RIMBA Experiments

This repository contains the scripts and tools to reproduce the RIMBA experiments
and generate results, tables, and figures.

## Repository structure

- `rimba/`: RIMBA library submodule.
- `reproduce.py`: experiment launcher.
- `tools/`: evaluation, analysis, and rendering tools.
- `results/`: generated tables, figures, and reports.

## Requirements

- Linux x86_64 and an NVIDIA GPU with a CUDA-compatible driver and NVML support.
- CUDA Toolkit with `nvcc` and CUDA C++20 support.
- A C++23 compiler with OpenMP support.
- CMake **4.2 or newer**, Make, Git, and GNU `time` at `/usr/bin/time`.
- Python **3.12** with NumPy, Matplotlib, Pillow, and Open3D CPU.
- Open3D runtime libraries: `libegl1`, `libgl1`, and `libgomp1` on Ubuntu.
- LaTeX with PGFPlots and the usual table/layout packages. On Ubuntu, install
  `texlive-latex-extra`, `texlive-pictures`, and `texlive-fonts-recommended`.

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

### Datasets

- [KITTI odometry](https://www.cvlibs.net/datasets/kitti/eval_odometry.php):
  sequences `03` (801 frames), `05` (2761), `06` (1101), `07` (1101), and
  `10` (1201), with calibration and ground-truth poses.
- [MaiCity](https://www.ipb.uni-bonn.de/data/mai-city-dataset/): sequences
  `01` and `02`, 100 frames each, with calibration and ground-truth poses.
  Sequence `01` is reconstructed; sequence `02` supplies the independent
  quality reference.

Each dataset root must contain binary float32 XYZI scans and calibration:

```text
sequences/<sequence>/
├── velodyne/000000.bin, 000001.bin, ...
└── calib.txt
```

Poses can be at `poses/<sequence>.txt` or `sequences/<sequence>/poses.txt`.
The script handles both layouts without modifying the datasets.

Set the two dataset roots:

```bash
export RI_KITTI_DATASET=/path/to/kitti/odometry/dataset
export RI_MAICITY_DATASET=/path/to/maicity/bin
```

Alternatively, put the datasets or symlinks at `datasets/kitti` and
`datasets/maicity` in this checkout.

## Reproduce the paper experiments

```bash
python3 reproduce.py
```

For a short trial run, with a chosen results folder:

```bash
python3 reproduce.py --diagnostic-frame-count 20 --output results/trial
```

Add `--dry-run` to check the setup and preview the commands before starting.

The script builds RIMBA and runs the experiments. It generates the reference
cloud from all 100 MaiCity `02` scans and downloads the
[TanksAndTemples](https://github.com/RuanJY/TanksAndTemples) evaluator on the
first run.

Results are saved in a new folder under `results/paper_protocol/`:

- **`report.pdf`**: the tables and figures, arranged as in the paper.
- `report.tex`: the LaTeX source of the report.
- `data/` and `figures/`: the CSV data and quality-map images.

Timings will vary with your hardware. Quality scores may also differ slightly
because the evaluator samples points from the mesh randomly.

### Comparisons with other methods

Results from other methods and matched qualitative views can be added using
the files below. The report marks missing comparisons.

<details>
<summary>Adding comparison results and qualitative views</summary>

Place the files in `comparisons/` before running `reproduce.py`:

- `quality.csv`: columns `method`, `precision`, `recall`, `f1`, `tau_m`,
  `voxel_size_m`, `sample_points`, and `source`. Scores use [0, 1]. Use a
  0.10 m tolerance, 0.05 m voxel size, and 6,553,600 sampled mesh points.
- `runtime.csv`: columns `dataset` (`kitti` or `maicity`), `sequence`,
  `method`, `frames`, `time_ms_per_frame`, `hardware`, and `source`.
- `qualitative.pdf`: matched views, with their source described in
  `qualitative-source.txt`.

</details>

## Related repositories

- [RIMBA](https://github.com/rimba-meshing/rimba): algorithm and library.
- [RIMBA Meshing](https://github.com/rimba-meshing): project organization.

## Paper and citation

The RIMBA paper is in preparation.

- **Paper link:** to be added.
- **Citation:** BibTeX entry to be added after publication.

## License

[MIT License](LICENSE).
