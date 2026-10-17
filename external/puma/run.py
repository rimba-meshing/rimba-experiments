"""PUMA incremental mapping from sequence poses and unfiltered scans."""
import shutil
import sys

import numpy as np
import open3d as o3d
import yaml

from external.common import timing
from external.common.case import finish, load_case
from external.common.data import timestamps
from external.common.process import execute
from .poses import prepare


def inputs(case):
    root = case.output / "input" / case.workload.dataset / "ply"
    sequence = root / "sequences" / case.workload.sequence
    scans = sequence / "velodyne"
    scans.mkdir(parents=True)
    (root / "poses").mkdir()
    for index in range(case.workload.frames):
        points = np.fromfile(case.workload.directory / "velodyne" / f"{index:06d}.bin", dtype=np.float32).reshape((-1, 4))[:, :3]
        cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points.astype(np.float64)))
        if not o3d.io.write_point_cloud(str(scans / f"{index:06d}.ply"), cloud):
            raise ValueError("PUMA input conversion failed")
    prepare(case.workload.directory / "poses.txt", root / "poses" / (case.workload.sequence + ".txt"),
            case.workload.frames, case.workload.dataset == "maicity")
    shutil.copyfile(case.workload.directory / "calib.txt", sequence / "calib.txt")
    (sequence / "times.txt").write_text("".join(f"{value:.12g}\n" for value in timestamps(case.workload)))
    return root


def run(case):
    dataset = inputs(case)
    config = yaml.safe_load((case.root / "external/puma/config/puma.yml").read_text())
    config["out_dir"] = str(case.output / "reconstruction")
    path = case.output / "puma.yml"
    path.write_text(yaml.safe_dump(config))
    trace = case.output / "frame_timings.csv"
    execute([sys.executable, str(case.source / "apps/pipelines/mapping/build_gt_mesh_incremental.py"),
             "--config", str(path), "--dataset", str(dataset), "--sequence", case.workload.sequence,
             "--n_scans", str(case.workload.frames), "--timing-file", str(trace)], case.output / "node.log", case.source / "apps")
    meshes = list((case.output / "reconstruction").rglob("*_cropped_gt.ply"))
    if len(meshes) != 1:
        raise ValueError(f"Expected one final PUMA mesh; found {len(meshes)}")
    finish(case, meshes[0], timing.from_csv(trace, "compute_ms", "puma", case.workload.frames))


if __name__ == "__main__":
    run(load_case())
