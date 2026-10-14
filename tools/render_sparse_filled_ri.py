#!/usr/bin/env python3
"""Render the sparse and filled native RI for one debug-dumped frame."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import PowerNorm


BACKGROUND = "#ffffff"
NULL_COLOR = "#000000"


def read_metadata(path: Path) -> dict[str, str | int | float]:
    values: dict[str, str | int | float] = {}
    for line in path.read_text().splitlines():
        key, raw_value = line.split(maxsplit=1)
        try:
            values[key] = int(raw_value)
        except ValueError:
            try:
                values[key] = float(raw_value)
            except ValueError:
                values[key] = raw_value
    return values


def read_range(path: Path, height: int, width: int) -> np.ndarray:
    values = np.fromfile(path, dtype=np.float32)
    expected = height * width
    if values.size != expected:
        raise ValueError(f"Expected {expected} range values in {path}, got {values.size}")
    return values.reshape(height, width).astype(np.float64)


def configure_axis(axis: object, width: int, height: int, show_ylabel: bool) -> None:
    ticks_x = np.asarray([0, width // 4, width // 2, 3 * width // 4, width - 1])
    ticks_y = np.asarray([0, height // 4, height // 2, 3 * height // 4, height - 1])
    axis.set_xticks(
        ticks_x,
        [str(value) for value in ticks_x],
    )
    axis.set_yticks(ticks_y, [str(value) for value in ticks_y])
    axis.set_xlabel("Pixel column", color="black", fontsize=20)
    if show_ylabel:
        axis.set_ylabel("Pixel row", color="black", fontsize=20)
    axis.tick_params(colors="black", labelsize=18)
    for spine in axis.spines.values():
        spine.set_color("black")


def draw_range_image(
    axis: object,
    ranges: np.ndarray,
    normalization: PowerNorm,
    upside_down: bool,
    show_ylabel: bool,
) -> None:
    displayed = np.flipud(ranges) if upside_down else ranges
    colormap = plt.get_cmap("viridis").copy()
    colormap.set_bad(NULL_COLOR)
    masked = np.ma.masked_invalid(displayed)
    axis.set_facecolor(BACKGROUND)
    axis.imshow(
        masked,
        cmap=colormap,
        norm=normalization,
        interpolation="none",
        origin="upper",
        aspect="equal",
    )
    configure_axis(axis, ranges.shape[1], ranges.shape[0], show_ylabel)


def enlarge_sparse_markers(ranges: np.ndarray, footprint_px: int) -> np.ndarray:
    """Expand sparse samples only in the rendered copy, with azimuth wrapping."""
    if footprint_px <= 1:
        return ranges
    radius = footprint_px // 2
    expanded = ranges.copy()
    for row_offset in range(-radius, radius + 1):
        for col_offset in range(-radius, radius + 1):
            if row_offset == 0 and col_offset == 0:
                continue
            shifted = np.roll(
                ranges, shift=(row_offset, col_offset), axis=(0, 1)
            ).copy()
            if row_offset > 0:
                shifted[:row_offset, :] = np.nan
            elif row_offset < 0:
                shifted[row_offset:, :] = np.nan
            fill = ~np.isfinite(expanded) & np.isfinite(shifted)
            expanded[fill] = shifted[fill]
    return expanded


def render_single(
    ranges: np.ndarray,
    normalization: PowerNorm,
    output: Path,
    upside_down: bool,
    dpi: int,
) -> None:
    figure, axis = plt.subplots(figsize=(8.0, 8.0), facecolor=BACKGROUND)
    draw_range_image(axis, ranges, normalization, upside_down, show_ylabel=True)
    figure.subplots_adjust(left=0.20, right=0.92, bottom=0.15, top=0.97)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=dpi, facecolor=figure.get_facecolor())
    plt.close(figure)


def render_pair(
    sparse: np.ndarray,
    filled: np.ndarray,
    normalization: PowerNorm,
    output: Path,
    upside_down: bool,
    dpi: int,
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(14.0, 7.4), facecolor=BACKGROUND)
    draw_range_image(axes[0], sparse, normalization, upside_down, show_ylabel=True)
    draw_range_image(axes[1], filled, normalization, upside_down, show_ylabel=False)
    axes[0].set_title("Sparse RI", color="black", pad=8)
    axes[1].set_title("After filling", color="black", pad=8)
    figure.subplots_adjust(left=0.04, right=0.99, bottom=0.09, top=0.93, wspace=0.08)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=dpi, facecolor=figure.get_facecolor())
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug-dir", type=Path,
        required=True,
        help="Directory written by --debug-filled-ri-dir.",
    )
    parser.add_argument("--label", default="iterative-5")
    parser.add_argument("--frame", type=int, default=50)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--color-min", type=float, default=3.0)
    parser.add_argument("--color-max", type=float, default=20.0)
    parser.add_argument("--color-gamma", type=float, default=1.0)
    parser.add_argument(
        "--sparse-marker-pixels", type=int, default=3,
        help="Square visual-only footprint for sparse RI returns; 1 keeps raw pixels.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Output PNG resolution.")
    parser.add_argument("--normal", action=argparse.BooleanOptionalAction, default=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.color_min <= 0.0 or args.color_min >= args.color_max:
        raise SystemExit("--color-min must be positive and smaller than --color-max")
    if args.sparse_marker_pixels <= 0 or args.sparse_marker_pixels % 2 == 0:
        raise SystemExit("--sparse-marker-pixels must be a positive odd number")
    if args.dpi <= 0:
        raise SystemExit("--dpi must be positive")
    debug_dir = args.debug_dir.expanduser().resolve()
    stem = f"{args.label}_frame_{args.frame:06d}"
    metadata = read_metadata(debug_dir / f"{stem}_range.txt")
    height, width = int(metadata["height"]), int(metadata["width"])
    sparse = read_range(debug_dir / f"{stem}_scan_range.f32", height, width)
    filled = read_range(debug_dir / f"{stem}_range.f32", height, width)
    sparse_display = enlarge_sparse_markers(sparse, args.sparse_marker_pixels)
    normalization = PowerNorm(
        gamma=args.color_gamma,
        vmin=args.color_min,
        vmax=args.color_max,
        clip=True,
    )
    output_dir = (args.output_dir or debug_dir / "figures").expanduser().resolve()
    prefix = f"maicity_01_frame_{args.frame:06d}_ri"
    sparse_path = output_dir / f"{prefix}_sparse.png"
    filled_path = output_dir / f"{prefix}_filled.png"
    pair_path = output_dir / f"{prefix}_sparse_vs_filled.png"
    render_single(sparse_display, normalization, sparse_path, not args.normal, args.dpi)
    render_single(filled, normalization, filled_path, not args.normal, args.dpi)
    render_pair(
        sparse_display, filled, normalization, pair_path, not args.normal, args.dpi
    )
    figure_metadata = {
        "frame": args.frame,
        "source_debug_dir": str(debug_dir),
        "label": args.label,
        "ri_shape": [height, width],
        "colormap": "viridis",
        "color_range_m": [args.color_min, args.color_max],
        "color_gamma": args.color_gamma,
        "sparse_marker_footprint_pixels": args.sparse_marker_pixels,
        "sparse_marker_expansion_visual_only": True,
        "export_dpi": args.dpi,
        "sparse_valid_pixels": int(np.count_nonzero(np.isfinite(sparse))),
        "filled_valid_pixels": int(np.count_nonzero(np.isfinite(filled))),
        "filled_pixels_added": int(
            np.count_nonzero(np.isfinite(filled) & ~np.isfinite(sparse))
        ),
        "orientation": "normal" if args.normal else "upside_down",
        "outputs": {
            "sparse": str(sparse_path),
            "filled": str(filled_path),
            "pair": str(pair_path),
        },
    }
    metadata_path = output_dir / f"{prefix}_metadata.json"
    metadata_path.write_text(json.dumps(figure_metadata, indent=2) + "\n")
    print(json.dumps(figure_metadata, indent=2))


if __name__ == "__main__":
    main()
