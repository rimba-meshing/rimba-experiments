"""CAD-Mesher mapping with one acknowledgement per replayed update."""
import os
import re
import shutil
import time

from external.common import timing
from external.common.case import finish, load_case
from external.common.data import sequence_view
from external.common.process import execute
from external.common.ros import Session, stop
from external.common.workspace import build, built_environment


def replay_command(case, sequence):
    python = os.environ.get("RIMBA_CAD_MESHER_PYTHON", os.environ.get("RIMBA_ROS_PYTHON", "/usr/bin/python3"))
    dataset = "maicity_bin" if case.workload.dataset == "maicity" else "kitti_odom"
    command = [python, str(case.root / "external/cad_mesher/replay.py"), "--dataset", dataset,
               "--velodyne-dir", str(sequence / "velodyne"), "--poses", str(sequence / "poses.txt"),
               "--calib", str(sequence / "calib.txt"), "--times", str(sequence / "times.txt"),
               "--max-frames", str(case.workload.frames), "--rate", "1000", "--replay-mode", "ack"]
    return command


def run(case):
    workspace = build(case)
    environment = built_environment(case, workspace)
    sequence = sequence_view(case)
    config = "maicity.yaml" if case.workload.dataset == "maicity" else "kitti_meshing.yaml"
    prefix = case.output / "cad_mesher_result" / config.removesuffix(".yaml") / "kitti"
    prefix.mkdir(parents=True)
    with Session(case, environment) as ros:
        ros.parameters(case.root / "external/cad_mesher/config" / config, {
            "/cad_mesher/seq": "/" + case.workload.sequence, "/cad_mesher/file_loc_report": prefix,
            "/cad_mesher/file_loc_dataset": sequence, "/cad_mesher/max_steps": case.workload.frames})
        node = ros.start(["rosrun", "cad_mesher", "cad_mesher"], "node")
        time.sleep(3)
        execute(replay_command(case, sequence), case.output / "replay.log", env=ros.environment)
        text = (case.output / "replay.log").read_text(errors="replace")
        delivered = re.search(r"published_frames=(\d+)", text)
        if not delivered or int(delivered[1]) != case.workload.frames:
            raise ValueError("CAD replay did not deliver the requested interval")
        time.sleep(5)
        stop(node)
        if node.returncode not in (0, -2):
            raise RuntimeError("CAD-Mesher failed; see node.log")
    reports = list((case.output / "cad_mesher_result").rglob("*_report.txt"))
    meshes = list((case.output / "cad_mesher_result").rglob(case.workload.sequence + "_mesh.ply"))
    if len(reports) != 1 or len(meshes) != 1:
        raise ValueError("Missing/ambiguous CAD mesh or native report")
    report = case.output / "upstream_report.txt"
    shutil.copyfile(reports[0], report)
    finish(case, meshes[0], timing.from_report(report, "cad_mesher", case.workload.frames))


if __name__ == "__main__":
    run(load_case())
