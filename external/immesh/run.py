"""Headless ImMesh mapping using the paper's sequence-pose patch."""
import os
import sys
import time

from external.common import timing
from external.common.case import finish, load_case
from external.common.data import lidar_poses
from external.common.process import execute
from external.common.ros import Session, stop
from external.common.workspace import build, built_environment


def wait_idle(case, node):
    previous, stable = None, 0
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if node.poll() is not None:
            raise RuntimeError("ImMesh stopped before completing replay; see node.log")
        files = [case.output / "ImMesh_output" / name for name in ("mesh_cost_time.log", "lio_state.log")]
        current = [(p.stat().st_mtime_ns, p.stat().st_size) for p in files if p.is_file()]
        stable = stable + 1 if current and current == previous else 0
        if stable >= 2:
            return
        previous = current
        time.sleep(1)
    raise RuntimeError("ImMesh logs did not become idle after replay")


def run(case):
    workspace = build(case)
    environment = built_environment(case, workspace)
    environment["RIMBA_IMMESH_OUTPUT_ROOT"] = str(case.output)
    environment["PYTHONPATH"] = str(case.root) + os.pathsep + environment.get("PYTHONPATH", "")
    python = os.environ.get("RIMBA_IMMESH_PYTHON", os.environ.get("RIMBA_ROS_PYTHON", "/usr/bin/python3"))
    execute([python, "-m", "external.immesh.bag", sys.argv[1]], case.output / "bag.log", case.root, environment)
    poses = lidar_poses(case)
    maicity = case.workload.dataset == "maicity"
    with Session(case, environment) as ros:
        ros.parameters(case.root / "external/immesh/config/velodyne.yaml", {
            "/gui_font_size": 20, "/publish/effect_point_pub": False, "/meshing/if_draw_mesh": 0,
            "/meshing/distance_scale": 1.0 if maicity else 1.5, "/preprocess/blind": 0.5 if maicity else 1.0,
            "/mapping/external_pose_en": True, "/mapping/external_pose_path": poses})
        node = ros.start(["rosrun", "ImMesh", "ImMesh_mapping"], "node")
        ros.wait_node("/laserMapping", node)
        execute(["rosbag", "play", str(case.output / "input.bag")], case.output / "replay.log", env=ros.environment)
        wait_idle(case, node)
        stop(node)
        if node.returncode not in (0, -2):
            raise RuntimeError("ImMesh failed while exporting; see node.log")
    trace = case.output / "ImMesh_output/mesh_cost_time.log"
    values = []
    for line in trace.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) == 5:
            try:
                int(fields[0])
                values.append(float(fields[1]))
            except ValueError:
                continue
    finish(case, case.output / "ImMesh_output/rec_mesh.ply",
           timing.summary("immesh", values, case.workload.frames, str(trace.relative_to(case.output))),
           {"quality_pose_correction": "pose[1] @ inverse(pose[0])" if maicity else "none"})


if __name__ == "__main__":
    run(load_case())
