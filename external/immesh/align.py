"""Apply the paper's pose-index correction to the MaiCity ImMesh export."""
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

from external.common.case import write_json


def align(source, poses, target):
    rows = np.loadtxt(poses, dtype=np.float64).reshape((-1, 3, 4))
    if len(rows) < 2:
        raise ValueError("ImMesh quality alignment requires at least two poses")
    matrices = np.repeat(np.eye(4)[None], 2, axis=0)
    matrices[:, :3, :4] = rows[:2]
    transform = matrices[1] @ np.linalg.inv(matrices[0])
    mesh = o3d.io.read_triangle_mesh(str(source))
    mesh.transform(transform)
    if not o3d.io.write_triangle_mesh(str(target), mesh):
        raise ValueError("Could not save aligned ImMesh mesh")
    write_json(target.with_suffix(".json"), {"convention": "pose[1] @ inverse(pose[0])", "transform": transform.tolist()})


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise ValueError("Expected source mesh, LiDAR poses and aligned mesh path")
    align(*(Path(value) for value in sys.argv[1:]))
