"""Accumulate the independent MaiCity 02 reference without loading it all at once."""
from __future__ import annotations

import hashlib
from pathlib import Path


def points(path: Path):
    import numpy as np
    raw = np.fromfile(path, dtype="<f4")
    if not raw.size or raw.size % 4:
        raise ValueError(f"Invalid XYZI scan: {path}")
    xyz = raw.reshape(-1, 4)[:, :3]
    if not np.isfinite(xyz).all():
        raise ValueError(f"Non-finite scan coordinates: {path}")
    # Preserve the original preparation: filter zero range in float32, then
    # transform in float64 and serialize XYZ as little-endian float32.
    return xyz[np.sqrt(np.sum(xyz ** 2, axis=1)) > 0].astype(np.float64)


def matrix(values: str):
    import numpy as np
    numbers = np.fromstring(values, sep=" ", dtype=np.float64)
    if numbers.size != 12 or not np.isfinite(numbers).all():
        raise ValueError("Expected a finite 3x4 pose/calibration matrix")
    return np.vstack((numbers.reshape(3, 4), [0., 0., 0., 1.]))


def generate(dataset: Path, destination: Path) -> dict:
    import numpy as np
    from ..paper_results.common import sha256
    directory = dataset / "sequences/02"
    scans = [directory / "velodyne" / f"{i:06d}.bin" for i in range(100)]
    poses = (directory / "poses.txt").read_text().splitlines()
    calibration = next((line.split(":", 1)[1] for line in (directory / "calib.txt").read_text().splitlines() if line.startswith("Tr:")), None)
    if len(poses) < 100 or calibration is None:
        raise ValueError("MaiCity 02 requires 100 poses and a Tr: calibration")
    transform = matrix(calibration)
    inverse = np.linalg.inv(transform)
    # Count valid vertices first so the PLY needs no post-write header patch.
    count = sum(len(points(scan)) for scan in scans)
    header = (f"ply\nformat binary_little_endian 1.0\nelement vertex {count}\n"
              "property float x\nproperty float y\nproperty float z\nend_header\n").encode("ascii")
    if destination.exists():
        raise ValueError(f"Reference destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    digest = hashlib.sha256(header)
    written = 0
    inputs = []
    print("Preparing MaiCity 02 global reference (100 scans).", flush=True)
    with temporary.open("xb") as stream:
        stream.write(header)
        for index, scan in enumerate(scans):
            xyz = points(scan)
            pose = inverse @ matrix(poses[index]) @ transform
            homogeneous = np.hstack((xyz, np.ones((len(xyz), 1))))
            transformed = (pose @ homogeneous.T).T
            block = (transformed[:, :3] / transformed[:, 3:]).astype("<f4").tobytes()
            stream.write(block)
            digest.update(block)
            written += len(xyz)
            inputs.append({"frame": index, "sha256": sha256(scan)})
    if written != count:
        raise ValueError("MaiCity 02 changed while generating its reference")
    temporary.rename(destination)
    record = {"sequence": "02", "frames": 100, "vertices": count, "sha256": digest.hexdigest(),
              "format": "binary_little_endian float32 XYZ", "pose_transform": "inv(Tr) @ pose @ Tr",
              "poses_sha256": sha256(directory / "poses.txt"), "calibration_sha256": sha256(directory / "calib.txt"),
              "scans": inputs}
    print(f"Reference: {count:,} points; SHA-256 {record['sha256']}", flush=True)
    return record
