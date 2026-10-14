# Verified container environment

Verified on 2026-10-14 from a clean GitHub clone of the experiments repository.
RIMBA executables were compiled inside the container. The container used
read-only dataset mounts and the host NVIDIA driver; no host RIMBA executable
or Python virtual environment was used.

## Tested snapshot

- Source: `fb94b2a9cd6c1b62f3166b8ce4a76b32e7f6a962`.
- Protocol: experiments `63b48255535232904c3a94721cf97ab9b681e025`.
- Ubuntu 24.04 x86_64; GCC 13.3.0; CMake 4.2.3; Python 3.12.3.
- CUDA Toolkit 13.2.0, NVCC 13.2.51, native GPU architecture.
- NVIDIA RTX 4060 Laptop, 8188 MiB; driver 595.91.07;
  NVIDIA Container Toolkit 1.20.1.
- Plotting and evaluation packages are pinned in the Docker requirements.
  The unmodified evaluator revision is `06f6537b471fd939eaed78678b3c0ebd22bd398a`.

This records one working combination. Other toolchains and GPU architectures
require their own verification.

## Results of verification

The full protocol completed KITTI 07 frames 0–1100 and MaiCity 01 frames 0–99,
with 3 warmups and 10 measured throughput repetitions for each scheduler
configuration. All 18 throughput, memory, and stage-timing sections completed,
along with three MaiCity quality evaluations. The result checker validated
60 raw throughput samples, their derived statistics, all frame intervals,
six process-memory traces, and the quality artifacts.

All six output PLY files matched the retained reference campaign byte for
byte by SHA-256. Quality F1 differences were below 0.0003; mesh sampling in the
evaluator is random. Runtime and memory values depend on the host hardware,
driver, and load. Verification outputs have not been selected as paper results.

Fresh frame-50 range capture reproduced the retained sparse/completed range
arrays and their three PNGs byte for byte. The three native scan PNGs also
matched. The top-down mesh renderer ran successfully. Short-interval runs and
deliberately altered statistics were used to check validation failures.

## Current test limitations

CPU Debug compilation succeeds, with 4/8 tests passing. Assertion failures
remain in `stitch_candidates_tests`, `stitch_matching_tests`,
`stitch_connection_tests`, and `hole_filling_tests`. These failures are present
in the unchanged implementation and require separate investigation.

The verification covers the RIMBA protocol and static method figures.
External-method comparisons and manuscript typesetting/capture workflows
require separate reconstructions, tools, and inputs.
