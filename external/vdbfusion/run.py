"""Fixed-pose VDBFusion reconstruction with the paper configuration."""
import csv
import json
import time

import numpy as np
import open3d as o3d
from vdbfusion import VDBVolume

from external.common import timing
from external.common.case import finish, load_case
from external.common.poses import _read_tr


def reconstruct(case, config):
    rows = np.loadtxt(case.workload.directory / "poses.txt", dtype=np.float64).reshape((-1, 3, 4))
    poses = np.repeat(np.eye(4)[None], len(rows), axis=0)
    poses[:, :3, :4] = rows
    calibration = np.array(_read_tr(case.workload.directory / "calib.txt"), dtype=np.float64)
    poses = np.einsum("ij,njk,kl->nil", np.linalg.inv(calibration), poses, calibration)
    volume = VDBVolume(voxel_size=config["voxel_size"], sdf_trunc=config["sdf_trunc"], space_carving=config["space_carving"])
    rows = []
    for index in range(case.workload.frames):
        points = np.fromfile(case.workload.directory / "velodyne" / f"{index:06d}.bin", dtype=np.float32).reshape((-1, 4))[:, :3].astype(np.float64)
        ranges = np.linalg.norm(points, axis=1)
        points = points[(ranges >= config["min_range"]) & (ranges <= config["max_range"])]
        pose = poses[index]
        world = points @ pose[:3, :3].T + pose[:3, 3]
        started = time.perf_counter()
        volume.integrate(world.astype(np.float64), pose.astype(np.float64))
        rows.append({"frame_index": index, "integration_ms": 1000 * (time.perf_counter() - started)})
    vertices, triangles = volume.extract_triangle_mesh(fill_holes=config["fill_holes"], min_weight=config["min_weight"])
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices), o3d.utility.Vector3iVector(triangles))
    mesh.compute_vertex_normals()
    target = case.output / "mesh.ply"
    if not o3d.io.write_triangle_mesh(str(target), mesh):
        raise ValueError("VDBFusion could not write its reconstruction")
    trace = case.output / "frame_timings.csv"
    with trace.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["frame_index", "integration_ms"])
        writer.writeheader()
        writer.writerows(rows)
    finish(case, target, timing.from_csv(trace, "integration_ms", "vdbfusion", case.workload.frames))


if __name__ == "__main__":
    case = load_case()
    reconstruct(case, json.loads((case.root / "external/vdbfusion/config.json").read_text()))
