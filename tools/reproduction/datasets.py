"""Read-only dataset validation and a temporary normalized layout."""
from __future__ import annotations

import os
from pathlib import Path

from ..paper_results.runtime import EXTRA_KITTI

COUNTS = {"kitti": {"07": 1101, **EXTRA_KITTI}, "maicity": {"01": 100, "02": 100}}


def sources(root: Path) -> dict:
    output = {}
    for kind, sequences in COUNTS.items():
        variable = "RI_" + kind.upper() + "_DATASET"
        dataset = Path(os.environ.get(variable, root / "datasets" / kind)).expanduser().resolve()
        selected = {}
        for sequence, count in sequences.items():
            directory = dataset / "sequences" / sequence
            poses = directory / "poses.txt"
            if not poses.is_file():
                poses = dataset / "poses" / f"{sequence}.txt"
            for path in (poses, directory / "calib.txt"):
                if not path.is_file():
                    raise ValueError(f"Missing input: {path}. Set {variable}; see README.md#datasets.")
            if len(poses.read_text().splitlines()) < count:
                raise ValueError(f"Expected at least {count} poses: {poses}")
            for index in range(count):
                scan = directory / "velodyne" / f"{index:06d}.bin"
                if not scan.is_file() or scan.stat().st_size == 0 or scan.stat().st_size % 16:
                    raise ValueError(f"Missing or invalid float32 XYZI scan: {scan}")
            selected[sequence] = {"velodyne": directory / "velodyne", "poses.txt": poses, "calib.txt": directory / "calib.txt"}
        output[kind] = selected
    return output


def stage(selected: dict, work: Path) -> dict[str, Path]:
    roots = {}
    for kind, sequences in selected.items():
        roots[kind] = work / "datasets" / kind
        for sequence, files in sequences.items():
            directory = roots[kind] / "sequences" / sequence
            directory.mkdir(parents=True)
            for name, target in files.items():
                (directory / name).symlink_to(target, target_is_directory=target.is_dir())
    return roots
