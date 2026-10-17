"""Deterministic top-down error maps using the manuscript rasterization rules."""
from __future__ import annotations
from array import array
import math
from pathlib import Path
import struct
from typing import Iterable, Sequence
import zlib

QUALITY_MAP_WIDTH = 1200
QUALITY_MAP_BACKGROUND = (220, 224, 226)

PLY_SCALAR_FORMATS = {
    "char": "b",
    "uchar": "B",
    "int8": "b",
    "uint8": "B",
    "short": "h",
    "ushort": "H",
    "int16": "h",
    "uint16": "H",
    "int": "i",
    "uint": "I",
    "int32": "i",
    "uint32": "I",
    "float": "f",
    "float32": "f",
    "double": "d",
    "float64": "d",
}


def read_ply_layout(path: Path) -> tuple[int, int, struct.Struct, dict[str, int]]:
    with path.open("rb") as stream:
        vertex_count: int | None = None
        in_vertex_element = False
        properties: list[tuple[str, str]] = []
        while True:
            raw_line = stream.readline()
            if not raw_line:
                raise ValueError(f"Incomplete PLY header: {path}")
            line = raw_line.decode("ascii").strip()
            if line == "format binary_little_endian 1.0":
                continue
            if line.startswith("element "):
                fields = line.split()
                in_vertex_element = len(fields) == 3 and fields[1] == "vertex"
                if in_vertex_element:
                    vertex_count = int(fields[2])
                continue
            if line.startswith("property ") and in_vertex_element:
                fields = line.split()
                if len(fields) != 3 or fields[1] not in PLY_SCALAR_FORMATS:
                    raise ValueError(f"Unsupported vertex property in {path}: {line}")
                properties.append((fields[2], PLY_SCALAR_FORMATS[fields[1]]))
                continue
            if line == "end_header":
                break
        if vertex_count is None:
            raise ValueError(f"PLY has no vertex element: {path}")
        names = {name: index for index, (name, _) in enumerate(properties)}
        required = {"x", "y", "red", "green", "blue"}
        if not required.issubset(names):
            raise ValueError(f"PLY lacks colored XY points: {path}")
        record = struct.Struct("<" + "".join(code for _, code in properties))
        return stream.tell(), vertex_count, record, names


def iter_colored_ply(path: Path) -> Iterable[tuple[float, float, int, int, int]]:
    offset, vertex_count, record, names = read_ply_layout(path)
    yielded = 0
    with path.open("rb") as stream:
        stream.seek(offset)
        while yielded < vertex_count:
            count = min(65_536, vertex_count - yielded)
            data = stream.read(count * record.size)
            if len(data) != count * record.size:
                raise ValueError(f"Truncated PLY vertex data: {path}")
            for values in record.iter_unpack(data):
                yield (
                    float(values[names["x"]]),
                    float(values[names["y"]]),
                    int(values[names["red"]]),
                    int(values[names["green"]]),
                    int(values[names["blue"]]),
                )
            yielded += count


def colored_ply_extent(paths: Sequence[Path]) -> tuple[float, float, float, float]:
    xmin = ymin = math.inf
    xmax = ymax = -math.inf
    for path in paths:
        for x, y, _, _, _ in iter_colored_ply(path):
            xmin = min(xmin, x)
            xmax = max(xmax, x)
            ymin = min(ymin, y)
            ymax = max(ymax, y)
    if not all(math.isfinite(value) for value in (xmin, xmax, ymin, ymax)):
        raise ValueError("Quality-map PLY files contain no finite XY extent")
    padding = 0.02 * max(xmax - xmin, ymax - ymin)
    return xmin - padding, xmax + padding, ymin - padding, ymax + padding


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum)
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def write_rgb_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    if len(pixels) != width * height * 3:
        raise ValueError("RGB canvas size does not match its dimensions")
    scanlines = bytearray()
    stride = width * 3
    for row in range(height):
        scanlines.append(0)
        scanlines.extend(pixels[row * stride : (row + 1) * stride])
    payload = bytearray(b"\x89PNG\r\n\x1a\n")
    payload.extend(png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
    payload.extend(png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)))
    payload.extend(png_chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def render_quality_map(
    source: Path,
    destination: Path,
    extent: tuple[float, float, float, float],
) -> tuple[int, int]:
    xmin, xmax, ymin, ymax = extent
    width = QUALITY_MAP_WIDTH
    height = max(1, round(width * (ymax - ymin) / (xmax - xmin)))
    pixel_count = width * height
    pixels = bytearray(QUALITY_MAP_BACKGROUND) * pixel_count
    scores = array("H", [0]) * pixel_count
    occupied = bytearray(pixel_count)
    for x, y, red, green, blue in iter_colored_ply(source):
        column = min(width - 1, max(0, int((x - xmin) / (xmax - xmin) * (width - 1))))
        row = min(height - 1, max(0, int((ymax - y) / (ymax - ymin) * (height - 1))))
        index = row * width + column
        score = 3 * 255 - red - green - blue
        if not occupied[index] or score >= scores[index]:
            offset = index * 3
            pixels[offset : offset + 3] = bytes((red, green, blue))
            scores[index] = score
            occupied[index] = 1

    dilated = bytearray(pixels)
    dilated_scores = array("H", scores)
    dilated_occupied = bytearray(occupied)
    for index, present in enumerate(occupied):
        if not present:
            continue
        row, column = divmod(index, width)
        neighbours = []
        if column > 0:
            neighbours.append(index - 1)
        if column + 1 < width:
            neighbours.append(index + 1)
        if row > 0:
            neighbours.append(index - width)
        if row + 1 < height:
            neighbours.append(index + width)
        for neighbour in neighbours:
            if not dilated_occupied[neighbour] or scores[index] >= dilated_scores[neighbour]:
                source_offset = index * 3
                target_offset = neighbour * 3
                dilated[target_offset : target_offset + 3] = pixels[source_offset : source_offset + 3]
                dilated_scores[neighbour] = scores[index]
                dilated_occupied[neighbour] = 1
    write_rgb_png(destination, width, height, dilated)
    return width, height
