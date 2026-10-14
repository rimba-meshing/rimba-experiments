#!/usr/bin/env python3
"""Render one native-resolution scan and its spherical range image.

The point cloud and range image use one shared power-law range normalization
over a fixed 3-20 m interval and the same colormap. By default the cloud comes
from MaiCity 01 and the RI comes from the denser MaiCity 02 scan, projected
into the same 64x1024 grid. If several
input points land in one pixel, the nearest point is kept for the RI.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import PowerNorm


BACKGROUND = "#000000"
RI_PAPER_BACKGROUND = "#ffffff"
RI_NULL_COLOR = "#000000"


@dataclass(frozen=True)
class RenderConfig:
    """Parameters shared by the point-cloud and RI renderers."""

    width: int
    height: int
    fov_min_rad: float
    fov_max_rad: float
    colormap: str
    upside_down: bool
    point_size: float
    elev: float
    azim: float
    cloud_focus_range: float
    ri_source_label: str
    dpi: int


def read_scan(path: Path) -> np.ndarray:
    """Read a KITTI-style float32 ``x, y, z, intensity`` scan."""
    values = np.fromfile(path, dtype=np.float32)
    if values.size == 0 or values.size % 4 != 0:
        raise ValueError(f"Malformed scan (expected groups of four floats): {path}")
    points = values.reshape(-1, 4)[:, :3]
    valid = np.all(np.isfinite(points), axis=1)
    points = points[valid]
    if len(points) == 0:
        raise ValueError(f"Scan contains no finite points: {path}")
    return np.ascontiguousarray(points, dtype=np.float64)


def project_to_native_ri(
    points: np.ndarray,
    config: RenderConfig,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Project points and retain the nearest range in each native RI pixel."""
    ranges = np.linalg.norm(points, axis=1)
    theta = np.arctan2(points[:, 1], points[:, 0])
    phi = np.arctan2(points[:, 2], np.hypot(points[:, 0], points[:, 1]))
    rows = np.floor(
        (phi - config.fov_min_rad)
        / (config.fov_max_rad - config.fov_min_rad)
        * config.height
        + 0.5
    ).astype(np.int64)
    cols = np.floor(
        (theta + math.pi) / (2.0 * math.pi) * config.width + 0.5
    ).astype(np.int64)
    cols = np.clip(cols, 0, config.width - 1)
    valid = (
        (rows >= 0)
        & (rows < config.height)
        & np.isfinite(ranges)
        & (ranges > 0.0)
    )

    ri = np.full(config.height * config.width, np.inf, dtype=np.float64)
    flat_pixels = rows[valid] * config.width + cols[valid]
    np.minimum.at(ri, flat_pixels, ranges[valid])
    ri[np.isinf(ri)] = np.nan
    ri = ri.reshape(config.height, config.width)
    collision_count = int(len(flat_pixels) - np.unique(flat_pixels).size)
    return ri, ranges, collision_count


def make_normalization(gamma: float, minimum: float, maximum: float) -> PowerNorm:
    """Use fixed power-law bounds to emphasize the selected distance band."""
    return PowerNorm(gamma=gamma, vmin=minimum, vmax=maximum, clip=True)


def resolve_vertical_fov(
    points: np.ndarray,
    height: int,
    minimum_deg: float | None,
    maximum_deg: float | None,
) -> tuple[float, float]:
    """Use explicit limits or infer the effective native sensor FOV."""
    if (minimum_deg is None) != (maximum_deg is None):
        raise ValueError("--elev-min-deg and --elev-max-deg must be used together")
    if minimum_deg is not None and maximum_deg is not None:
        if minimum_deg >= maximum_deg:
            raise ValueError("--elev-min-deg must be smaller than --elev-max-deg")
        return math.radians(minimum_deg), math.radians(maximum_deg)

    phi = np.degrees(np.arctan2(points[:, 2], np.hypot(points[:, 0], points[:, 1])))
    minimum, maximum = float(np.min(phi)), float(np.max(phi))
    half_pixel = (maximum - minimum) / (2.0 * height)
    return math.radians(minimum - half_pixel), math.radians(maximum + half_pixel)


def select_cloud_focus(points: np.ndarray, ranges: np.ndarray, maximum: float) -> np.ndarray:
    """Return the near points used to frame the zoomed 3-D camera."""
    focus = points[ranges <= maximum]
    return focus if len(focus) >= 10 else points


def configure_3d_axes(
    ax: object,
    config: RenderConfig,
    focus_points: np.ndarray,
) -> None:
    """Match the established black-background point-cloud presentation."""
    lower = np.min(focus_points, axis=0)
    upper = np.max(focus_points, axis=0)
    extent = np.maximum(upper - lower, 1e-3)
    padding = np.maximum(extent * 0.03, 0.05)
    ax.set_xlim(lower[0] - padding[0], upper[0] + padding[0])
    ax.set_ylim(lower[1] - padding[1], upper[1] + padding[1])
    ax.set_zlim(lower[2] - padding[2], upper[2] + padding[2])
    ax.set_box_aspect(extent)
    ax.view_init(elev=config.elev, azim=config.azim)
    ax.set_axis_off()


def configure_azimuth_axis(axis: object, width: int) -> None:
    """Label horizontal RI pixels with their corresponding azimuth angle."""
    positions = np.linspace(0, width - 1, 7)
    degrees = np.linspace(-180.0, 180.0, 7)
    axis.set_xticks(positions, [f"{angle:.0f}°" for angle in degrees])
    axis.set_xlabel("Azimuth (°)")


def render_point_cloud(
    points: np.ndarray,
    ranges: np.ndarray,
    normalization: PowerNorm,
    config: RenderConfig,
    output: Path,
) -> None:
    """Render the raw point cloud with distance-based colors."""
    figure = plt.figure(figsize=(10.5, 8.0), facecolor=BACKGROUND)
    axis = figure.add_subplot(111, projection="3d", facecolor=BACKGROUND)
    axis.scatter(
        points[:, 0], points[:, 1], points[:, 2],
        c=ranges,
        cmap=config.colormap,
        norm=normalization,
        s=config.point_size,
        linewidths=0.0,
        alpha=0.95,
    )
    focus_points = select_cloud_focus(points, ranges, config.cloud_focus_range)
    configure_3d_axes(axis, config, focus_points)
    plt.tight_layout(pad=0.2)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=config.dpi, facecolor=figure.get_facecolor())
    plt.close(figure)


def render_range_image(
    ri: np.ndarray,
    normalization: PowerNorm,
    config: RenderConfig,
    output: Path,
) -> None:
    """Render the native RI without resizing or interpolation."""
    displayed = np.flipud(ri) if config.upside_down else ri
    colormap = plt.get_cmap(config.colormap).copy()
    colormap.set_bad(RI_NULL_COLOR)
    masked = np.ma.masked_invalid(displayed)
    figure, axis = plt.subplots(
        figsize=(18.0, 3.2),
        facecolor=RI_PAPER_BACKGROUND,
    )
    axis.set_facecolor(RI_PAPER_BACKGROUND)
    axis.imshow(
        masked,
        cmap=colormap,
        norm=normalization,
        interpolation="none",
        origin="upper",
        aspect="auto",
    )
    configure_azimuth_axis(axis, config.width)
    axis.set_ylabel("Elevation channel")
    axis.xaxis.label.set_color("black")
    axis.yaxis.label.set_color("black")
    axis.tick_params(colors="black")
    for spine in axis.spines.values():
        spine.set_color("black")
    figure.subplots_adjust(left=0.03, right=0.99, bottom=0.20, top=0.96)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=config.dpi, facecolor=figure.get_facecolor())
    plt.close(figure)


def render_pair(
    points: np.ndarray,
    ranges: np.ndarray,
    ri: np.ndarray,
    normalization: PowerNorm,
    config: RenderConfig,
    output: Path,
) -> None:
    """Render a compact overview containing both views without a legend."""
    displayed = np.flipud(ri) if config.upside_down else ri
    colormap = plt.get_cmap(config.colormap).copy()
    colormap.set_bad(BACKGROUND)
    figure = plt.figure(figsize=(18.0, 8.0), facecolor=BACKGROUND)
    grid = figure.add_gridspec(1, 2, width_ratios=(1.0, 1.25), wspace=0.04)
    cloud_axis = figure.add_subplot(grid[0, 0], projection="3d", facecolor=BACKGROUND)
    cloud_axis.scatter(
        points[:, 0], points[:, 1], points[:, 2],
        c=ranges, cmap=config.colormap, norm=normalization,
        s=config.point_size, linewidths=0.0, alpha=0.95,
    )
    focus_points = select_cloud_focus(points, ranges, config.cloud_focus_range)
    configure_3d_axes(cloud_axis, config, focus_points)
    cloud_axis.set_title(
        f"Point cloud · zoom ≤ {config.cloud_focus_range:.0f} m", color="white"
    )
    image_axis = figure.add_subplot(grid[0, 1], facecolor=BACKGROUND)
    image_axis.imshow(
        np.ma.masked_invalid(displayed), cmap=colormap, norm=normalization,
        interpolation="none", origin="upper", aspect="auto",
    )
    image_axis.set_title(
        f"Native RI · {config.ri_source_label} · "
        f"{config.height} × {config.width}",
        color="white",
    )
    configure_azimuth_axis(image_axis, config.width)
    image_axis.set_ylabel("Elevation channel")
    image_axis.tick_params(colors="white")
    for spine in image_axis.spines.values():
        spine.set_color("white")
    figure.subplots_adjust(left=0.01, right=0.99, bottom=0.08, top=0.90)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=config.dpi, facecolor=figure.get_facecolor())
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path,
        required=True,
        help="KITTI-style dataset root.",
    )
    parser.add_argument("--sequence", default="01")
    parser.add_argument("--frame", type=int, default=50)
    parser.add_argument(
        "--ri-sequence", default="02",
        help="Sequence used only to build the range image.",
    )
    parser.add_argument(
        "--ri-frame", type=int,
        help="Frame used only for the range image; defaults to --frame.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ri-width", type=int, default=1024)
    parser.add_argument("--ri-height", type=int, default=64)
    parser.add_argument(
        "--elev-min-deg", type=float,
        help="Override the inferred sensor FOV minimum elevation.",
    )
    parser.add_argument(
        "--elev-max-deg", type=float,
        help="Override the inferred sensor FOV maximum elevation.",
    )
    parser.add_argument("--cmap", default="viridis")
    parser.add_argument(
        "--color-gamma", type=float, default=1,
        help="Power-law exponent; lower values emphasize short distances.",
    )
    parser.add_argument("--color-min", type=float, default=3)
    parser.add_argument("--color-max", type=float, default=20.0)
    parser.add_argument(
        "--point-size", type=float, default=4.5,
        help="Matplotlib marker area in points squared for the 3-D cloud.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Output PNG resolution.")
    parser.add_argument("--view-elev", type=float, default=25.0)
    parser.add_argument("--view-azim", type=float, default=30.0)
    parser.add_argument(
        "--cloud-focus-range", type=float, default=8.0,
        help="Near-range limit used to frame the zoomed point-cloud view.",
    )
    parser.add_argument("--upside-down", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.ri_width <= 0 or args.ri_height <= 0:
        raise SystemExit("RI dimensions must be positive")
    if args.cloud_focus_range <= 0.0:
        raise SystemExit("--cloud-focus-range must be positive")
    if args.point_size <= 0.0:
        raise SystemExit("--point-size must be positive")
    if args.dpi <= 0:
        raise SystemExit("--dpi must be positive")
    if args.color_gamma <= 0.0:
        raise SystemExit("--color-gamma must be positive")
    if args.color_min <= 0.0 or args.color_min >= args.color_max:
        raise SystemExit("--color-min must be positive and smaller than --color-max")
    output_dir = args.output_dir or Path(
        f"results/figures/native_scan_{args.sequence}_frame_{args.frame:06d}"
    )
    cloud_scan_path = (
        args.dataset.expanduser()
        / "sequences"
        / args.sequence
        / "velodyne"
        / f"{args.frame:06d}.bin"
    )
    ri_frame = args.frame if args.ri_frame is None else args.ri_frame
    ri_scan_path = (
        args.dataset.expanduser()
        / "sequences"
        / args.ri_sequence
        / "velodyne"
        / f"{ri_frame:06d}.bin"
    )
    points = read_scan(cloud_scan_path)
    range_points = read_scan(ri_scan_path)
    cloud_ranges = np.linalg.norm(points, axis=1)
    # Infer the sensor FOV from the HDL-64 cloud.  The dense sequence contains
    # auxiliary near-origin returns that are useful for filling the RI but do
    # not describe the physical vertical extent of the sensor.
    fov_min_rad, fov_max_rad = resolve_vertical_fov(
        points, args.ri_height, args.elev_min_deg, args.elev_max_deg
    )
    config = RenderConfig(
        width=args.ri_width,
        height=args.ri_height,
        fov_min_rad=fov_min_rad,
        fov_max_rad=fov_max_rad,
        colormap=args.cmap,
        upside_down=args.upside_down,
        point_size=args.point_size,
        elev=args.view_elev,
        azim=args.view_azim,
        cloud_focus_range=args.cloud_focus_range,
        ri_source_label=f"dense seq {args.ri_sequence}",
        dpi=args.dpi,
    )
    ri, _, collision_count = project_to_native_ri(range_points, config)
    normalization = make_normalization(
        args.color_gamma, args.color_min, args.color_max
    )
    stem = f"maicity_{args.sequence}_frame_{args.frame:06d}"
    render_point_cloud(
        points, cloud_ranges, normalization, config,
        output_dir / f"{stem}_point_cloud.png",
    )
    render_range_image(
        ri, normalization, config, output_dir / f"{stem}_range_image.png"
    )
    render_pair(
        points, cloud_ranges, ri, normalization, config,
        output_dir / f"{stem}_pair.png",
    )
    metadata = {
        "dataset": str(args.dataset.expanduser().resolve()),
        "sequence": args.sequence,
        "frame": args.frame,
        "cloud_scan": str(cloud_scan_path.resolve()),
        "range_scan": str(ri_scan_path.resolve()),
        "point_count": int(len(points)),
        "range_point_count": int(len(range_points)),
        "range_sequence": args.ri_sequence,
        "range_frame": ri_frame,
        "ri_shape": [config.height, config.width],
        "vertical_fov_deg": [math.degrees(fov_min_rad), math.degrees(fov_max_rad)],
        "vertical_fov_source": "cloud scan sensor extent",
        "colormap": config.colormap,
        "color_scale": "power-law",
        "color_gamma": normalization.gamma,
        "color_range_m": [normalization.vmin, normalization.vmax],
        "cloud_focus_range_m": config.cloud_focus_range,
        "point_size_pt2": config.point_size,
        "export_dpi": config.dpi,
        "cloud_focus_point_count": int(
            len(select_cloud_focus(points, cloud_ranges, config.cloud_focus_range))
        ),
        "normalization_m": [normalization.vmin, normalization.vmax],
        "valid_ri_pixels": int(np.count_nonzero(np.isfinite(ri))),
        "ri_pixel_collisions": collision_count,
        "orientation": "upside_down" if config.upside_down else "normal",
    }
    (output_dir / f"{stem}_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
