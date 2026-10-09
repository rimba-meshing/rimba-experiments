# RIMBA Experiments

This repository contains the protocols, launch scripts, and analysis utilities
used to reproduce and inspect RIMBA measurements. It covers the current paper
protocol for throughput, scheduler ablations, memory, stage timings, and an
optional geometric-quality evaluation.

The RIMBA implementation is included as the `rimba/` Git submodule. Each
experiments-repository revision therefore records the source revision selected
for that protocol snapshot. This repository does not include the KITTI or
MaiCity datasets, and generated run outputs are ignored by Git by default.

## Repositories

- [RIMBA](https://github.com/rimba-meshing/rimba): C++23/CUDA algorithm,
  executable, public headers, and tests. Included here as the `rimba/` submodule.
- [RIMBA Experiments](https://github.com/rimba-meshing/rimba-experiments):
  protocols and tooling in this repository.
- [RIMBA Meshing organization](https://github.com/rimba-meshing): home of the
  RIMBA repositories.

## Repository layout

- `rimba/`: pinned source checkout used by the protocol.
- `protocols/paper_protocol.md`: experiment definitions, datasets, variants,
  measurement boundaries, and interpretation guidance.
- `tools/run_paper_protocol.py`: configures builds, runs measurements, and
  collects logs and output tables.
- `tools/benchmark_statistics.py`: summarizes repeated throughput runs and
  computes confidence intervals.
- `tools/evaluate_maicity_tnt.py`: optional MaiCity evaluation using the
  modified Tanks and Temples evaluator.
- `REPRODUCIBILITY.md`: machine requirements, dataset setup, commands, and
  output details.
- `results/`: local protocol output directory; ignored by Git.

## Quick start

Clone this repository with the source submodule initialized:

```bash
git clone --recurse-submodules https://github.com/rimba-meshing/rimba-experiments.git
cd rimba-experiments
```

If the repository was cloned without submodules, initialize them with:

```bash
git submodule update --init --recursive
```

Set the dataset roots on the machine where the measurements will run:

```bash
export RI_KITTI_DATASET=/path/to/kitti/odometry
export RI_MAICITY_DATASET=/path/to/maicity/bin
```

Inspect the planned commands without running the full protocol:

```bash
python3 tools/run_paper_protocol.py --dry-run --skip-quality
```

Run the configured protocol into a new timestamped directory:

```bash
python3 tools/run_paper_protocol.py \
  --require-clean \
  --output "results/paper_protocol/$(date +%Y%m%d_%H%M%S)"
```

The full run builds and measures the main configuration and scheduler
variants, performs separate memory and stage-timing passes, and runs the
optional quality evaluation when a reference cloud and evaluator are
configured. Use `--help` to see options for selecting dataset paths, frame
ranges, repetitions, output locations, or individual protocol sections.

## Requirements and data

The complete protocol is intended for a Linux workstation with an NVIDIA GPU.
It requires CMake 4.2 or newer, a C++23-compatible host compiler, CUDA Toolkit
with `nvcc`, and Python 3.10 or newer for orchestration and analysis. CUDA
Toolkit 13.2.78 is the oldest version recorded in the development history;
treat it as a known baseline, not a verified minimum. Earlier versions have
not been tested against this repository. RIMBA builds host sources as C++23
and CUDA translation units as CUDA C++20. Select a host compiler supported by
the installed `nvcc`; NVIDIA documents the CUDA 13.2 host-compiler and platform
matrix in its
[Linux installation guide](https://docs.nvidia.com/cuda/archive/13.2.0/cuda-installation-guide-linux/index.html).
KITTI odometry and MaiCity data are downloaded separately and remain outside
this repository.

The protocol defaults to KITTI sequence `07` and MaiCity sequence `01`. It
checks the available contiguous frame files before running. The optional
Tanks and Temples quality pass also requires the modified evaluator checkout
and an independent MaiCity reference cloud. Configure the evaluator with
`RI_TNT_RUNNER` or `--quality-runner`, and provide the reference with
`RI_MAICITY_GROUND_TRUTH` or `--quality-ground-truth`.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the full setup procedure and
[protocols/paper_protocol.md](protocols/paper_protocol.md) for the exact
measurement plan and current configuration. The meshing implementation is
C++/CUDA; Python is used here for orchestration, evaluation integration, and
analysis. The workflow does not require an HPC system or a separate Python
implementation of the algorithm.

## Recorded outputs

Each run directory contains the commands and logs, a `metadata.json` manifest
with repository revisions and machine/GPU details, raw per-run timings, and
derived CSV summaries. Depending on the selected protocol sections, outputs
include throughput statistics, scheduler comparisons, stage timings, memory
samples, quality metrics, and inputs for qualitative figures.

Raw and diagnostic run directories under `results/` are not tracked by Git.
This keeps the experiment repository focused on the reproducibility protocol
and analysis code; only reviewed, publication-ready result artifacts should be
added deliberately when they are ready to share.

## Reproducibility notes

- Keep the `rimba/` submodule pointer unchanged when reproducing a run tied to
  this experiments-repository revision.
- Use `--require-clean` for a protocol run that should be associated with a
  clean source and experiments checkout.
- The runner records the source and experiment commits, commands, arguments,
  machine, and GPU in the output metadata.
- End-to-end throughput excludes dataset loading and final PLY writing. It
  includes the meshing call, GPU/host work, transfers, and synchronization.
- Stage timings are diagnostic and may add instrumentation overhead. Memory
  passes are separate from throughput runs; consult the protocol before
  comparing their measurements.

## Paper and citation

The paper describing RIMBA is in preparation.

- **Paper link:** To be added when the paper is publicly available.
- **Citation:** BibTeX entry to be added with the publication details.

## License

The experiment protocols and analysis tools in this repository are distributed
under the MIT License. See [LICENSE](LICENSE) for the full text.
