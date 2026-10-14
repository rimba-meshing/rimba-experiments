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

For a concrete environment with pinned versions, use the
[Docker workflow](docker/README.md). It starts from this repository's pinned
source and builds all executables in the container. Static figure dependencies
and commands are documented in [protocols/figures.md](protocols/figures.md).

- Linux workstation with an NVIDIA GPU
- CMake 4.2 or newer
- C++23-compatible host compiler, CUDA Toolkit with `nvcc`, and CUDA C++20
  support for CUDA translation units
- The container workflow uses CUDA Toolkit 13.2.0 (`nvcc V13.2.51`), GCC 13.3,
  CMake 4.2.3, and Python 3.12.3. Earlier CUDA releases have not been verified.
  See NVIDIA's [CUDA
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
  --keep-ablation-meshes \
  --output "results/paper_protocol/$(date +%Y%m%d_%H%M%S)"
```

The output directory contains the exact commands, build and run logs, source
and experiment commit IDs, machine and GPU details, raw per-run timings, and
derived CSV summaries. `results/` is ignored by Git; archive result bundles
separately when preparing a release or paper submission.

See [protocols/paper_protocol.md](protocols/paper_protocol.md) for measurement
boundaries, variants, quality settings, and interpretation of the statistics.

## Check the result bundle

For the complete KITTI 07 / MaiCity 01 sequences used in this protocol:

```bash
python3 tools/check_protocol.py results/paper_protocol/my-run \
  --expected-kitti-frames 1101 --expected-maicity-frames 100 \
  --output results/paper_protocol/my-run/verification.json
```

The check requires all 18 measurement sections, 3 warmups and 10 measured
repetitions for throughput, positive process-memory peaks, and all three
quality evaluations. It recomputes the throughput statistics from the saved
samples. Use `--skip-quality` when that optional evaluation was omitted.
For a short diagnostic interval, supply its actual frame counts. Nonstandard
repetitions require explicit `--expected-warmups` and `--expected-runs`.
The JSON report preserves the recorded source and experiments revisions and
states the checked intervals. Keep it with the logs and commands.
