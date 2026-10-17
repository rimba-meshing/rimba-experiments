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
- LaTeX with PGFPlots, `standalone`, and `booktabs`. On Ubuntu, install
  `texlive-latex-extra`, `texlive-pictures`, and `texlive-fonts-recommended`.
- Poppler's `pdftocairo` for browser previews (`poppler-utils` on Ubuntu).

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
creates `results/paper_protocol/<run>/index.html`. Open that file to browse
the results in the order of the paper's Evaluation section.

- `geometric_quality/`: quality tables, spatial error maps, and supplied views.
- `computational_performance/`: runtime, per-frame times, stages, and memory.
- `scheduling_ablation/`: scheduling performance and its effect on the output.
- `provenance.json`: measurement revisions, validation, and artifact checksums.
- `raw.tar.gz`: original measurements and technical logs.

Tables have CSV, LaTeX fragments, and PDF outputs. Figures have their source
data and PDF, with previews embedded in the index. Standalone LaTeX sources
are retained in the raw archive. The plots use the manuscript's PGFPlots
definitions. The index identifies generated outputs, partial
comparisons, omitted evaluations, and figures needing additional inputs.

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
- `--output PATH`: choose a new destination, including for `--report-only`.
- `--keep-meshes`: retain meshes outside the raw archive for inspection.
- `--paper-inputs FILE`: include supplied comparison results and matched views.
- `--help`: show all launcher options.

Convert an existing measurement directory or paper bundle without rerunning
the experiments:

```bash
python3 reproduce.py --report-only /path/to/run --output results/paper_from_existing
```

The original run is preserved. Its frame counts and quality setting are
detected automatically. `--diagnostic-frame-count` can enforce an expected
short interval during conversion.

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
The input files are retained with the archived evidence.

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
