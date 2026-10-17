"""Evaluate completed external reconstructions and supply the report tables."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from external import records
from external.common.case import LABELS, git, sha256, write_json
from external.common.process import execute
from ..paper_results.common import write_csv


def discover(root: Path, selected: dict, frame_count: int | None, dry_run: bool) -> dict | None:
    available = records.pointer(root, frame_count).is_file()
    if available:
        print("Checking the completed external campaign...", flush=True)
    result = records.discover(root, selected, frame_count, dry_run)
    if result:
        print(f"External comparisons: {result['directory']}", flush=True)
    else:
        print("No external campaign for this interval. The report will contain the RIMBA experiments only.", flush=True)
    return result


def runtime_rows(campaign: dict) -> list[dict]:
    hardware = campaign["manifest"]["environment"]["hardware"]["cpu"]
    rows = []
    for case in campaign["cases"]:
        native = case["timing"]
        rows.append({"method": LABELS[case["method"]], **{key: case["workload"][key] for key in ("dataset", "sequence", "frames")},
                     "time_ms_per_frame": native["time_ms_per_frame"], "native_frame_count": native["native_frame_count"],
                     "native_trace_complete": native["native_trace_complete"], "timing_scope": native["scope"],
                     "hardware": hardware, "source": case["source_commit"], "experiments_commit": case["experiments_commit"],
                     "image_id": case.get("image_id", ""), "recipe_sha256": case.get("recipe_sha256", "")})
    return rows


def evaluation(root: Path, case: dict, reference: Path, runner: Path) -> tuple[dict, Path]:
    mesh = case["mesh_path"]
    # Both reconstructions use the same immutable mesh/reference/evaluator.
    identity = [sha256(reference), git(runner.parents[2], "rev-parse", "HEAD"), case["mesh_sha256"],
                sha256(root / "tools/evaluate_maicity_tnt.py"), sha256(Path(__file__)), sha256(root / "external/immesh/align.py")]
    key = hashlib.sha256("\n".join(identity).encode()).hexdigest()
    directory = mesh.parent / "evaluation" / key
    metrics = directory / "quality/metrics.json"
    if not metrics.is_file():
        if directory.exists():
            raise ValueError(f"Incomplete external quality evaluation: {directory}; inspect/remove it before retrying")
        directory.mkdir(parents=True)
        environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
        if case["method"] == "immesh":
            if case.get("quality_pose_correction") != "pose[1] @ inverse(pose[0])":
                raise ValueError("ImMesh result does not record the expected sequence-pose convention")
            aligned = directory / "aligned.ply"
            execute([sys.executable, "-m", "external.immesh.align", str(mesh), str(mesh.parent / "sequence_poses_lidar.txt"), str(aligned)],
                    directory / "alignment.log", root, environment)
            mesh = aligned
        command = [sys.executable, str(root / "tools/evaluate_maicity_tnt.py"), "--ground-truth", str(reference),
                   "--mesh", str(mesh), "--output", str(directory / "quality"), "--evaluator-runner", str(runner)]
        execute(command, directory / "quality.log", root, environment)
    return json.loads(metrics.read_text()), directory


def supply(root: Path, campaign: dict, raw: Path, runner: Path) -> None:
    destination = raw / "external_comparisons"
    destination.mkdir()
    write_json(destination / "campaign.json", campaign["manifest"])
    write_json(raw / "external_campaign.json", {"experiments_commit": campaign["manifest"]["experiments_commit"],
               "sources": campaign["manifest"]["sources"],
               "images": {key: value.get("image_id", "") for key, value in campaign["manifest"]["environment"]["methods"].items()}, "protocol_sha256": campaign["manifest"]["protocol_sha256"]})
    write_csv(destination / "runtime.csv", runtime_rows(campaign))
    quality = []
    reference = raw.parent / "maicity_reference.ply"
    reference_sha = sha256(reference)
    for case in campaign["cases"]:
        if case["workload"]["dataset"] != "maicity":
            continue
        print(f"Quality evaluation: {LABELS[case['method']]}", flush=True)
        metrics, evaluated = evaluation(root, case, reference, runner)
        if metrics["status"] != "ok" or metrics["evaluator_repository"]["commit"] != git(runner.parents[2], "rev-parse", "HEAD"):
            raise ValueError("External quality evaluator does not match the RIMBA evaluator")
        quality.append({"method": LABELS[case["method"]], **{key: metrics[key] for key in ("precision", "recall", "f1", "tau_m", "voxel_size_m", "sample_points")},
                        "source": case["source_commit"], "mesh_sha256": case["mesh_sha256"], "reference_sha256": reference_sha,
                        "evaluator_commit": metrics["evaluator_repository"]["commit"], "experiments_commit": case["experiments_commit"],
                        "image_id": case.get("image_id", ""), "recipe_sha256": case.get("recipe_sha256", "")})
        evidence = destination / case["method"]
        evidence.mkdir()
        shutil.copyfile(case["result_path"], evidence / "result.json")
        shutil.copyfile(evaluated / "quality/metrics.json", evidence / "metrics.json")
        if (evaluated / "aligned.json").is_file():
            shutil.copyfile(evaluated / "aligned.json", evidence / "alignment.json")
    write_csv(destination / "quality.csv", quality)
    path = raw / "publication_inputs.json"
    supplied = json.loads(path.read_text()) if path.is_file() else {}
    if any(key in supplied for key in ("external_quality", "external_runtime")):
        raise ValueError("Remove legacy comparisons/quality.csv and runtime.csv when using a completed external campaign")
    supplied.update(external_quality="external_comparisons/quality.csv", external_runtime="external_comparisons/runtime.csv")
    write_json(path, supplied)
