"""Identify inputs and validate a completed external campaign before reuse."""
import hashlib
import json
from pathlib import Path

from tools.reproduction.datasets import COUNTS
from .common import timing
from .common.case import METHODS, git, mesh_counts, sha256


def mode(frame_count):
    return "full" if frame_count is None else f"diagnostic-{frame_count}"


def pointer(root, frame_count):
    return root / ".cache/external" / ("current-" + mode(frame_count) + ".json")


def protocol(root):
    files = sorted(path for path in (root / "external").rglob("*") if path.is_file()
                   and not any(part == "source" or part.startswith(".") for part in path.relative_to(root / "external").parts)
                   and path.suffix in {".py", ".patch", ".json", ".yml", ".yaml", ".txt", ".Dockerfile", ".cmake"})
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def input_identity(selected, frame_count):
    records = {}
    for dataset, sequences in selected.items():
        for sequence, files in sequences.items():
            count = 100 if (dataset, sequence) == ("maicity", "02") else (frame_count or COUNTS[dataset][sequence])
            digest = hashlib.sha256()
            for index in range(count):
                path = files["velodyne"] / f"{index:06d}.bin"
                digest.update(bytes.fromhex(sha256(path)))
            records[dataset + "/" + sequence] = {"frames": count, "scans_sha256": digest.hexdigest(),
                "poses_sha256": sha256(files["poses.txt"]), "calibration_sha256": sha256(files["calib.txt"]),
                "times_sha256": sha256(files["times.txt"]) if "times.txt" in files else "uniform 0.1 s"}
    return records


def cases(directory, manifest):
    output = []
    for relative in manifest["results"]:
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("External result path escapes its campaign directory")
        if sha256(path) != manifest["result_checksums"][relative]:
            raise ValueError(f"External result record changed: {path}")
        record = json.loads(path.read_text())
        native_path = (path.parent / record["timing"]["source"]).resolve()
        if not native_path.is_relative_to(path.parent) or sha256(native_path) != record["native_trace_sha256"]:
            raise ValueError(f"External native trace changed: {native_path}")
        mesh = path.parent / "mesh.ply"
        if record["schema"] != "rimba-external-case-v1" or sha256(mesh) != record["mesh_sha256"]:
            raise ValueError(f"External mesh does not match its recorded result: {mesh}")
        if mesh_counts(mesh) != {key: record[key] for key in ("vertices", "faces")}:
            raise ValueError(f"External mesh counts disagree: {mesh}")
        if record["experiments_commit"] != manifest["experiments_commit"]:
            raise ValueError("External case experiment revision differs from its campaign")
        if record["source_commit"] != manifest["sources"][record["method"]]:
            raise ValueError("External case source differs from its campaign")
        method_image = manifest.get("environment", {}).get("methods", {}).get(record["method"], {})
        if record.get("image_id") != method_image.get("image_id") or record.get("recipe_sha256") != method_image.get("recipe_sha256"):
            raise ValueError("External case image differs from its campaign")
        workload = record["workload"]
        native = record["timing"]
        if not timing.accepted(record["method"], native["native_frame_count"], workload["frames"]):
            raise ValueError("External native trace does not meet the paper protocol")
        import math
        if not math.isfinite(native["time_ms_per_frame"]) or native["time_ms_per_frame"] <= 0:
            raise ValueError("Invalid external native timing")
        output.append({**record, "mesh_path": mesh, "result_path": path})
    expected = {(method, dataset, sequence, manifest["frame_count"] or count)
                for method in METHODS for dataset, sequences in COUNTS.items()
                for sequence, count in sequences.items() if (dataset, sequence) != ("maicity", "02")}
    actual = [(row["method"], row["workload"]["dataset"], row["workload"]["sequence"], row["workload"]["frames"]) for row in output]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("External campaign is incomplete or contains duplicate workloads")
    return output


def discover(root, selected, frame_count, dry_run=False):
    path = pointer(root, frame_count)
    if not path.is_file():
        return None
    directory = Path(json.loads(path.read_text())["directory"])
    manifest = json.loads((directory / "campaign.json").read_text())
    if manifest.get("schema") != "rimba-external-campaign-v1" or manifest.get("status") != "complete" or manifest["frame_count"] != frame_count:
        raise ValueError("External campaign is not a completed run of this interval")
    sources = {method: git(root / "external" / method / "source", "rev-parse", "HEAD") for method in METHODS}
    if manifest["sources"] != sources or manifest["protocol_sha256"] != protocol(root):
        raise ValueError("External method sources/adapters changed; rerun reproduce_external.py")
    if not dry_run and manifest["inputs"] != input_identity(selected, frame_count):
        raise ValueError("External campaign used different dataset contents; rerun reproduce_external.py")
    rows = cases(directory, manifest)
    return {"directory": directory, "manifest": manifest, "cases": rows}
