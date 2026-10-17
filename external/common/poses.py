#!/usr/bin/env python3
"""Small KITTI-pose helpers shared by the external-pose runners."""

from __future__ import annotations

from pathlib import Path


Matrix = list[list[float]]


def _identity() -> Matrix:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    return [
        [sum(left[row][inner] * right[inner][column] for inner in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _rigid_inverse(matrix: Matrix) -> Matrix:
    inverse = _identity()
    for row in range(3):
        for column in range(3):
            inverse[row][column] = matrix[column][row]
    for row in range(3):
        inverse[row][3] = -sum(inverse[row][column] * matrix[column][3] for column in range(3))
    return inverse


def _read_pose_rows(path: Path) -> list[list[float]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        values = [float(value) for value in line.split()]
        if len(values) != 12:
            raise ValueError(f"{path}:{line_number} must contain 12 pose values, got {len(values)}")
        rows.append(values)
    if not rows:
        raise ValueError(f"Pose file is empty: {path}")
    return rows


def _read_tr(calib_path: Path) -> Matrix:
    for line in calib_path.read_text(encoding="utf-8").splitlines():
        key, separator, payload = line.partition(":")
        if separator and key.strip() == "Tr":
            values = [float(value) for value in payload.split()]
            if len(values) != 12:
                raise ValueError(f"{calib_path} has an invalid Tr record")
            matrix = _identity()
            matrix[0] = values[0:4]
            matrix[1] = values[4:8]
            matrix[2] = values[8:12]
            return matrix
    raise ValueError(f"Calibration has no Tr record: {calib_path}")


def _row_to_matrix(values: list[float]) -> Matrix:
    matrix = _identity()
    matrix[0] = values[0:4]
    matrix[1] = values[4:8]
    matrix[2] = values[8:12]
    return matrix


def write_lidar_pose_file(source_pose_path: Path, calibration_path: Path, destination: Path) -> int:
    """Convert camera-frame KITTI poses to LiDAR-frame poses and write them."""

    tr = _read_tr(calibration_path)
    tr_inverse = _rigid_inverse(tr)
    rows = _read_pose_rows(source_pose_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output_lines = []
    for values in rows:
        lidar_pose = _multiply(_multiply(tr_inverse, _row_to_matrix(values)), tr)
        output_lines.append(
            " ".join(f"{lidar_pose[row][column]:.17g}" for row in range(3) for column in range(4))
        )
    destination.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return len(output_lines)
