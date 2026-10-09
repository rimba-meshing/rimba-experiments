# Reproducibility

This repository records the local workstation protocol for building RIMBA,
running its scheduler and throughput measurements, and generating analysis
tables. It does not require an HPC system or a separate Python implementation
of the meshing method.

## Pinned source

The `rimba/` Git submodule records the exact RIMBA commit associated with this
experiment revision. Initialize it with `git clone --recurse-submodules` or:

```bash
git submodule update --init --recursive
```

The run manifest records commits and working-tree status for both repositories.
Keep the `rimba` submodule pointer unchanged when reproducing a published run.

## Requirements

- Linux workstation with an NVIDIA GPU
- CMake 4.2 or newer
- C++23-compatible host compiler, CUDA Toolkit with `nvcc`, and CUDA C++20
  support for CUDA translation units
- CUDA Toolkit 13.2.78 is the oldest version recorded in the development
  history; treat it as a known baseline, not a verified minimum. Earlier
  versions have not been tested against this repository. See NVIDIA's [CUDA
  13.2 Linux installation
  guide](https://docs.nvidia.com/cuda/archive/13.2.0/cuda-installation-guide-linux/index.html)
  for its supported host compiler and platform matrix.
- Python 3.10 or newer for orchestration and analysis
- KITTI odometry and MaiCity datasets downloaded separately

The optional Tanks and Temples quality evaluation also needs the evaluator
checkout and its Python dependencies. Supply its `run.py` path through
`RI_TNT_RUNNER` or `--quality-runner`.

## Dataset paths

Set the dataset roots for your machine. The protocol defaults to KITTI
sequence `07` and MaiCity sequence `01` and checks that their frame indices are
contiguous.

```bash
export RI_KITTI_DATASET=/path/to/kitti/odometry/dataset
export RI_MAICITY_DATASET=/path/to/maicity/bin
```

Only paths and frame ranges are recorded in the manifest. Dataset contents are
not copied into this repository.

## Run the protocol

Inspect the planned commands first:

```bash
python3 tools/run_paper_protocol.py --dry-run --skip-quality
```

Run the full throughput, scheduler, memory, and stage-timing protocol:

```bash
python3 tools/run_paper_protocol.py \
  --require-clean \
  --output "results/paper_protocol/$(date +%Y%m%d_%H%M%S)"
```

The output directory contains the exact commands, build and run logs, source
and experiment commit IDs, machine and GPU details, raw per-run timings, and
derived CSV summaries. `results/` is ignored by Git; archive result bundles
separately when preparing a release or paper submission.

See [protocols/paper_protocol.md](protocols/paper_protocol.md) for measurement
boundaries, variants, quality settings, and interpretation of the statistics.
