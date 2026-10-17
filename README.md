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

No arguments are required or accepted. The script:

1. Checks the dependencies and datasets.
2. Downloads [TanksAndTemples](https://github.com/RuanJY/TanksAndTemples)
   from `master` on first use and reuses the clean cached checkout.
3. Accumulates MaiCity `02` using its poses and calibration to generate
   the reference PLY. No prebuilt global point cloud is required.
4. Builds RIMBA and runs the runtime, memory, scheduling, and quality
   experiments, including the **0.30 m and 0.55 m** reconstructions.
5. Validates the measurements and generates the tables, plots, and four
   precision/recall map panels in a LaTeX/PDF report.

Results are written to `results/paper_protocol/full_<timestamp>/`:

- `report.pdf`: tables and figures grouped by the paper's Evaluation sections.
- `report.tex`: editable LaTeX source, with measured revisions and the
  generated reference checksum recorded in comments.
- `data/`: CSV data used in the tables and plots.
- `figures/`: quality-map images and any supplied matched views.

Temporary meshes, the reference PLY, logs, and metadata are removed after
successful export. A failed run retains its temporary files under `.work/`
for diagnosis. The evaluator stays in `.cache/TanksAndTemples`; the first
run requires internet access.

### Measurement protocol

- Runtime comparison: all five KITTI sequences and MaiCity `01`.
- Scheduling ablations, memory profiles, and stage timings: KITTI `07`
  and MaiCity `01`.
- Throughput: 3 warmups and 10 measured repetitions per configuration.
- The 0.55 m sensitivity pass uses the same reference scheduling policy,
  frame interval, reference cloud, and quality evaluator as the 0.30 m run.
  Only the shared continuity/triangle-edge threshold changes; stitching
  and hole-fill thresholds retain their defaults. This extra pass measures
  geometric quality, not comparative runtime.
- Quality: 0.10 m tolerance, 0.05 m voxel size, and 6,553,600 sampled mesh
  points, evaluated directly in global coordinates without registration.
- Meshing times exclude dataset loading and PLY writing. Memory and stage
  profiling are measured separately from throughput.
- Runtime and memory depend on hardware and load. Quality scores can vary
  slightly because the evaluator samples mesh points randomly.

### Comparisons and matched views

The script generates the RIMBA measurements and quantitative figures.
Comparisons with other methods require their own runs. If available, these
files are included automatically:

- `comparisons/quality.csv`
- `comparisons/runtime.csv`
- `comparisons/qualitative.pdf`, with its source described in
  `comparisons/qualitative-source.txt`

The report identifies missing comparisons or matched views explicitly.
Historical measurements are not substituted for new runs.

<details>
<summary>Comparison CSV columns</summary>

Quality columns: `method`, `precision`, `recall`, `f1`, `tau_m`,
`voxel_size_m`, `sample_points`, and `source`. Scores use [0, 1] and the
quality protocol above.

Runtime columns: `dataset` (`kitti` or `maicity`), `sequence`, `method`,
`frames`, `time_ms_per_frame`, `hardware`, and `source`.

</details>

The individual tools in `tools/` provide `--help` for custom diagnostics,
raw-data retention, re-exporting previous measurements, and additional method
illustrations. For example, `tools/report_protocol.py` can export an existing
measurement directory and retain its raw evidence with `--keep-raw`.

## Related repositories

- [RIMBA](https://github.com/rimba-meshing/rimba): algorithm and library.
- [RIMBA Meshing](https://github.com/rimba-meshing): project organization.

## Paper and citation

The RIMBA paper is in preparation.

- **Paper link:** to be added.
- **Citation:** BibTeX entry to be added after publication.

## License

[MIT License](LICENSE).
