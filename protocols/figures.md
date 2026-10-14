# Static method figures

All commands below run from the experiments repository with NumPy, Matplotlib,
and Pillow installed. For Python 3.12, install the versions in
`requirements-figures.txt` with the constraints in `requirements.lock.txt`.
Use the same versions and settings when
comparing rendered images; image file metadata can also affect byte hashes.

## Sparse and completed range images

The protocol builds `rimba/build/cuda-native-release/ri_meshing` with range
exports enabled. Starting with a fresh source checkout, it can also be built
with the documented source presets:

```bash
cmake -S rimba --preset cuda-release-native
cmake --build rimba/build/cuda-native-release -j2
```

Capture MaiCity sequence 01 frame 50 from the dataset, then render the raw
range arrays. This capture uses one frame with sequential scheduling because
filled-RI exports are incompatible with asynchronous pre-scan scheduling.

```bash
rimba/build/cuda-native-release/ri_meshing \
  --dataset "$RI_MAICITY_DATASET" --sequence 01 --frame 50 --frame-count 1 \
  --warmup-runs 0 --runs 1 --frame-overlap none \
  --output results/figures/ri-completion/frame50.ply \
  --debug-filled-ri-dir results/figures/ri-completion/raw \
  --debug-filled-ri-max-frames 1
python3 tools/render_sparse_filled_ri.py \
  --debug-dir results/figures/ri-completion/raw --frame 50 \
  --output-dir results/figures/ri-completion/images
```

The defaults use `viridis`, range 3–20 m, gamma 1, 300 dpi, inverted RI
orientation, and 20/18 pt axis/tick labels. Sparse samples have a visual-only
3-pixel footprint. The original range arrays remain unchanged. A JSON file
records the image dimensions, valid-pixel counts, display settings, and paths.

## Native point cloud and range image

```bash
python3 tools/render_native_scan_pair.py \
  --dataset "$RI_MAICITY_DATASET" --sequence 01 --ri-sequence 02 --frame 50 \
  --output-dir results/figures/native-scan
```

The point-cloud panel reads sequence 01. The denser sequence 02 provides the
RI panel. The default RI is 64×1024; sensor elevation bounds are inferred from
the sequence-01 scan. Camera, colour limits, point size, and input paths are
recorded in the output metadata. No mesh or historical image is needed.

## Top-down mesh image

```bash
python3 tools/render_mesh_xy_solid.py \
  results/paper_protocol/my-run/meshes/maicity_reference_pre_scan_polyline_throughput.ply \
  --output results/figures/mesh-xy.png --no-label \
  --bounds -5 55 -14 14
```

Select the same spatial bounds and image size for comparisons. This utility
renders triangular faces from an ASCII PLY. Exact qualitative comparisons
with external methods additionally require their reconstructions and matching
camera settings; those inputs are not provided by the RIMBA protocol.
