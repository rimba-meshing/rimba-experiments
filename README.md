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

### Quality evaluation

- Evaluator: [RuanJY/TanksAndTemples](https://github.com/RuanJY/TanksAndTemples).
- Use its `master` branch without local modifications.
- Python dependencies are included in the installation above.

```bash
git clone --branch master https://github.com/RuanJY/TanksAndTemples.git /path/to/TanksAndTemples
```

### Datasets

- **KITTI odometry:** sequences `03` (801 frames), `05` (2761), `06` (1101),
  `07` (1101), and `10` (1201).
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
creates `results/paper_protocol/<run>/report.pdf`. The report follows the
paper's Evaluation sections: geometric quality, computational performance,
and scheduling ablation. It contains the tables and figures, using the
manuscript's PGFPlots definitions.

- `report.pdf`: the complete results document.
- `report.tex`: editable LaTeX source, including the measured revisions.
- `data/`: the CSV data used in the tables and plots.
- `figures/`: quality-map images and supplied captures, when applicable.

The default output contains no HTML, logs, JSON metadata, or raw-data archive.
Temporary measurements and compiler files are removed after a successful
export. `--keep-raw` preserves them for later analysis and troubleshooting.
Missing comparison inputs and omitted evaluations are stated in the report.

- Variants: sequential, pre-scan, and pre-scan with the polyline blocker.
- Runtime comparison: the reference configuration on all five KITTI
  sequences and MaiCity 01. Ablations, memory profiles, and stage timings use
  KITTI 07 and MaiCity 01.
- Throughput: 3 warmups and 10 measured repetitions per variant.
- Memory, stage timings, and geometric quality are measured separately.
- Meshing times exclude dataset loading and PLY writing.
- Runtime and memory depend on hardware and load. Quality scores can vary
  slightly because the evaluator samples mesh points randomly.
- Comparisons with other methods require their own runs.

Useful options:

- `--skip-quality`: omit geometric-quality evaluation.
- `--diagnostic-frame-count 20`: use that many frames in every sequence.
- `--report-only PATH`: validate and summarize existing results.
- `--output PATH`: choose a new destination, including for `--report-only`.
- `--keep-raw`: add `raw.tar.gz` and `provenance.json` for detailed auditing
  and future re-export.
- `--keep-meshes`: retain meshes for inspection.
- `--paper-inputs FILE`: include supplied comparison results and matched views.
- `--help`: show all launcher options.

Convert an existing raw measurement directory or a bundle retained with
`--keep-raw` without rerunning the experiments:

```bash
python3 reproduce.py --report-only /path/to/run --output results/paper_from_existing
```

The original run is preserved. Its frame counts and quality setting are
detected automatically. Conversion uses only recorded measurements; it does
not fill missing KITTI sequences in older runs. The generated `report.tex`
can also be recompiled directly with LaTeX using its companion data/images.

<details>
<summary>Additional inputs for the full paper comparisons</summary>

The RIMBA run does not execute the external methods. Optional inputs are
listed in a JSON file, with paths relative to that file:

```json
{
  "external_quality": "quality.csv",
  "external_runtime": "runtime.csv",
  "sensitivity_results": "sensitivity_run",
  "qualitative_pdf": {"file": "matched_views.pdf", "source": "capture provenance"}
}
```

All fields are optional. Quality CSV columns are `method`, `precision`,
`recall`, `f1`, `tau_m`, `voxel_size_m`, `sample_points`, and `source`.
Scores use [0, 1]. Runtime columns are `dataset`, `sequence`, `method`,
`frames`, `time_ms_per_frame`, `hardware`, and `source`. Supplied values are
identified in their CSV provenance. A sensitivity directory must contain
the same evaluation protocol, source revision, and frame interval as the
reference run, recording `--max-triangle-dist 0.55` in both metadata and
the mesh-generation command (`tools/run_paper_protocol.py` supports it).
Matched views are supplied explicitly to preserve the paper's cameras/crops.
The input files are retained with the archived evidence when using `--keep-raw`.

</details>

The individual tools in `tools/` also provide `--help` for custom runs and
additional method illustrations.

## Related repositories

- [RIMBA](https://github.com/rimba-meshing/rimba): algorithm and library.
- [RIMBA Meshing](https://github.com/rimba-meshing): project organization.

## Paper and citation

The RIMBA paper is in preparation.

- **Paper link:** to be added.
- **Citation:** BibTeX entry to be added after publication.

## License

[MIT License](LICENSE).
