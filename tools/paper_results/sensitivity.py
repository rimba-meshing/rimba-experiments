"""Measure the paper's 0.55 m reconstruction with the reference scheduling policy."""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

from .common import VARIANTS, one, read_csv


def measure(args, binary: Path, parent_metadata: dict) -> None:
    try:
        import run_paper_protocol as protocol
    except ModuleNotFoundError:
        from tools import run_paper_protocol as protocol
    candidate = copy.copy(args)
    candidate.output = args.output / "sensitivity"
    candidate.max_triangle_dist = 0.55
    candidate.warmup_runs = candidate.runs = 1
    candidate.output.mkdir(parents=True, exist_ok=True)
    metadata = copy.deepcopy(parent_metadata)
    metadata.pop("finished_at", None)
    metadata["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    metadata["purpose"] = "Geometric sensitivity only; this pass is not a timing comparison."
    metadata["arguments"] = {key: str(value) if isinstance(value, Path) else value for key, value in vars(candidate).items()}
    manifest = candidate.output / "metadata.json"
    manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    spec = next(s for s in protocol.dataset_specs(candidate) if s["kind"] == "maicity")
    print(f"Geometric sensitivity: MaiCity {spec['sequence']}, {spec['count']} frames, 0.55 m", flush=True)
    row, summary, _, _, _, _ = protocol.run_application(candidate, spec, VARIANTS[-1], "throughput", binary, candidate.output, keep_mesh=True)
    row["status"] = "planned" if args.dry_run else "ok"
    row["output_mesh"] = str(candidate.output / "meshes/maicity_reference_pre_scan_polyline_throughput.ply")
    protocol.write_csv(candidate.output / "results.csv", [row])
    protocol.write_csv(candidate.output / "run_timings.csv", protocol.run_timing_rows_for(row, summary))
    protocol.write_csv(candidate.output / "quality.csv", protocol.run_optional_quality(candidate, [row], candidate.output, protocol.repository_root()))
    metadata["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest.write_text(json.dumps(metadata, indent=2) + "\n")


def validate(source: Path, metadata: dict) -> bool:
    if not metadata["arguments"].get("include_sensitivity"):
        return False
    from .quality import reference, sensitivity
    child = source / "sensitivity"
    sensitivity(child, reference(source))
    row = one(read_csv(child, "results.csv"), "0.55 m reconstruction")
    baseline = one((r for r in read_csv(source, "results.csv") if r["dataset"] == "maicity" and r["variant"] == VARIANTS[-1] and r["run_kind"] == "throughput"), "0.30 m reconstruction")
    if row["status"] != "ok" or row["dataset"] != "maicity" or row["variant"] != VARIANTS[-1]:
        raise ValueError("Invalid sensitivity reconstruction")
    for field in ("sequence", "start_frame", "frame_count", "frame_end"):
        if baseline[field] != row[field]:
            raise ValueError(f"Sensitivity reconstruction interval differs: {field}")
    if int(row["vertices"]) <= 0 or int(row["faces"]) <= 0:
        raise ValueError("Empty sensitivity reconstruction")
    return True
