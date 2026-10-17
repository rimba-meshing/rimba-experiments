"""Frame-limited views of the unmodified sequence inputs."""
from pathlib import Path

from .poses import write_lidar_pose_file


def timestamps(workload):
    path = workload.directory / "times.txt"
    values = [float(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []
    if values and len(values) < workload.frames:
        raise ValueError(f"Too few timestamps: {path}")
    return values[:workload.frames] if values else [i * 0.1 for i in range(workload.frames)]


def sequence_view(case, width=6):
    directory = case.output / "input" / case.workload.sequence
    scans = directory / "velodyne"
    scans.mkdir(parents=True)
    for index in range(case.workload.frames):
        (scans / f"{index:0{width}d}.bin").symlink_to(case.workload.directory / "velodyne" / f"{index:06d}.bin")
    for name in ("poses.txt", "calib.txt"):
        (directory / name).symlink_to(case.workload.directory / name)
    (directory / "times.txt").write_text("".join(f"{value:.12g}\n" for value in timestamps(case.workload)))
    return directory


def lidar_poses(case):
    target = case.output / "sequence_poses_lidar.txt"
    write_lidar_pose_file(case.workload.directory / "poses.txt", case.workload.directory / "calib.txt", target)
    return target
