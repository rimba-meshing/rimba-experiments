#!/usr/bin/env python3
"""Render a filled XY top-down view from an ASCII PLY triangle mesh."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rasterize PLY mesh faces into a solid XY top-down PNG."
    )
    parser.add_argument("ply", type=Path, help="Input ASCII PLY with vertices and triangular faces.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("mesh_xy_solid_faces_clean.png"),
        help="Output PNG path.",
    )
    parser.add_argument(
        "--bounds",
        nargs=4,
        type=float,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
        default=(-5.0, 55.0, -14.0, 14.0),
        help="XY crop bounds in mesh units. Default matches the initial-sequence view.",
    )
    parser.add_argument("--width", type=int, default=1800, help="Output image width in pixels.")
    parser.add_argument("--height", type=int, default=900, help="Output image height in pixels.")
    parser.add_argument(
        "--supersample",
        type=int,
        default=2,
        help="Rasterization supersampling factor used before downscaling.",
    )
    parser.add_argument(
        "--no-label",
        action="store_true",
        help="Do not draw the small metadata label in the top-left corner.",
    )
    parser.add_argument(
        "--max-faces",
        type=int,
        default=2_000_000,
        help="Maximum cropped faces to draw. Use 0 to draw every face.",
    )
    return parser.parse_args()


def read_ascii_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertex_count: int | None = None
    face_count: int | None = None
    header_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        first = handle.readline().strip()
        header_lines += 1
        if first != "ply":
            raise ValueError(f"{path} is not a PLY file")
        for line in handle:
            header_lines += 1
            if line.startswith("format ") and "ascii" not in line:
                raise ValueError("Only ASCII PLY files are supported")
            if line.startswith("element vertex"):
                vertex_count = int(line.split()[2])
            elif line.startswith("element face"):
                face_count = int(line.split()[2])
            elif line.strip() == "end_header":
                break

    if vertex_count is None or face_count is None:
        raise ValueError("PLY header must contain vertex and face counts")

    vertices = np.loadtxt(
        path,
        skiprows=header_lines,
        max_rows=vertex_count,
        usecols=(0, 1, 2),
        dtype=np.float32,
    )
    faces = np.loadtxt(
        path,
        skiprows=header_lines + vertex_count,
        max_rows=face_count,
        usecols=(1, 2, 3),
        dtype=np.int32,
    )
    if faces.ndim == 1:
        faces = faces.reshape(1, 3)
    return vertices, faces


def color_for_height(z: float, z_min: float, z_max: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, (z - z_min) / max(1.0e-6, z_max - z_min)))
    return (
        int(42 + 125 * t),
        int(78 + 120 * t),
        int(88 + 45 * (1.0 - t)),
    )


def render_solid_xy(
    vertices: np.ndarray,
    faces: np.ndarray,
    bounds: tuple[float, float, float, float],
    size: tuple[int, int],
    supersample: int,
    max_faces: int,
    label: str | None,
) -> Image.Image:
    xmin, xmax, ymin, ymax = bounds
    width, height = size
    scale = max(1, supersample)
    raster_width = width * scale
    raster_height = height * scale
    sx = (raster_width - 1) / (xmax - xmin)
    sy = (raster_height - 1) / (ymax - ymin)

    triangles = vertices[faces]
    keep = (
        (triangles[:, :, 0].max(axis=1) >= xmin)
        & (triangles[:, :, 0].min(axis=1) <= xmax)
        & (triangles[:, :, 1].max(axis=1) >= ymin)
        & (triangles[:, :, 1].min(axis=1) <= ymax)
    )
    triangles = triangles[keep]
    average_z = triangles[:, :, 2].mean(axis=1) if len(triangles) else np.array([], dtype=np.float32)

    z_min = float(vertices[:, 2].min())
    z_max = float(vertices[:, 2].max())
    image = Image.new("RGB", (raster_width, raster_height), (9, 10, 10))
    draw = ImageDraw.Draw(image)

    order = np.argsort(average_z)
    if max_faces > 0 and len(order) > max_faces:
        sample = np.linspace(0, len(order) - 1, max_faces, dtype=np.int64)
        order = order[sample]

    for index in order:
        points = [
            (
                int((float(x) - xmin) * sx),
                int(raster_height - 1 - ((float(y) - ymin) * sy)),
            )
            for x, y, _z in triangles[index]
        ]
        if len(set(points)) < 3:
            continue
        draw.polygon(points, fill=color_for_height(float(average_z[index]), z_min, z_max))

    if scale != 1:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.25))

    if label:
        draw = ImageDraw.Draw(image)
        text_width = min(width - 24, 12 + len(label) * 8)
        draw.rectangle((12, 12, text_width, 42), fill=(0, 0, 0))
        draw.text((20, 20), label, fill=(235, 240, 235))
    return image


def main() -> int:
    args = parse_args()
    vertices, faces = read_ascii_ply(args.ply)
    bounds = tuple(args.bounds)
    label = None
    if not args.no_label:
        label = (
            f"{args.output.name} | filled mesh faces only | "
            f"{len(faces):,} total faces | bounds x={bounds[0]:.1f}..{bounds[1]:.1f}, "
            f"y={bounds[2]:.1f}..{bounds[3]:.1f} | max_faces={args.max_faces}"
        )
    image = render_solid_xy(
        vertices=vertices,
        faces=faces,
        bounds=bounds,
        size=(args.width, args.height),
        supersample=args.supersample,
        max_faces=args.max_faces,
        label=label,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
