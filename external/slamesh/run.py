"""SLAMesh's fixed-pose sequence reader and native mesh export."""
import shutil

from external.common import timing
from external.common.case import finish, load_case
from external.common.data import lidar_poses, sequence_view
from external.common.ros import Session
from external.common.workspace import build, built_environment


def run(case):
    workspace = build(case)
    environment = built_environment(case, workspace)
    sequence = sequence_view(case, 5 if case.workload.dataset == "maicity" else 6)
    poses = lidar_poses(case)
    config = "maicity.yaml" if case.workload.dataset == "maicity" else "kitti_meshing.yaml"
    report = case.output / "slmsh"
    report.mkdir()
    with Session(case, environment) as ros:
        ros.parameters(case.root / "external/slamesh/config" / config, {
            "/slamesher/max_steps": case.workload.frames, "/slamesher/save_mesh_map": True,
            "/slamesher/external_pose_available": True, "/slamesher/external_pose_path": poses})
        node = ros.start(["rosrun", "slamesh", "slamesh", "_seq:=/" + case.workload.sequence,
                          "_file_loc_report:=" + str(report), "_file_loc_dataset:=" + str(sequence.parent)], "node")
        if node.wait(timeout=43200) != 0:
            raise RuntimeError("SLAMesh failed; see node.log")
    reports = list(case.output.glob("slmsh_*_report.txt"))
    if len(reports) != 1:
        raise ValueError("Missing/ambiguous SLAMesh native report")
    target = case.output / "upstream_report.txt"
    shutil.copyfile(reports[0], target)
    candidates = [case.output / (case.workload.sequence + "_mesh.ply"), report / (case.workload.sequence + "_mesh.ply")]
    mesh = next((path for path in candidates if path.is_file()), None)
    if mesh is None:
        raise ValueError("SLAMesh did not export a mesh")
    finish(case, mesh, timing.from_report(target, "slamesh", case.workload.frames))


if __name__ == "__main__":
    run(load_case())
