#!/usr/bin/env python3
"""Check completed protocol artifacts and recompute their throughput statistics.

This checks the configured frame intervals. Supply expected frame counts when
checking a full dataset; a valid short diagnostic run is not a full-sequence
measurement. No recorded results or execution metadata are modified.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
import sys

from benchmark_statistics import summarize


VARIANTS = ("scheduler_none", "scheduler_pre_scan", "reference_pre_scan_polyline")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def csv_rows(root: Path, name: str) -> list[dict[str, str]]:
    with (root / name).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(bool(rows), f"Empty table: {name}")
    return rows


def expected_run_ids(paper_output: bool = False) -> set[str]:
    suffixes = [f"{v}_throughput" for v in VARIANTS]
    suffixes += [f"{v}_memory_coarse" for v in VARIANTS]
    suffixes += ["scheduler_none_memory_detailed", "scheduler_none_stage_sequential"]
    if not paper_output:
        suffixes.append("reference_pre_scan_polyline_stage_overlap")
    return {f"{dataset}_{suffix}" for dataset in ("kitti", "maicity") for suffix in suffixes}


def check_runs(root: Path, expected_frames: dict[str, int | None], paper_output: bool = False) -> dict[str, dict[str, str]]:
    rows = csv_rows(root, "results.csv")
    by_id = {r["run_id"]: r for r in rows}
    require(len(by_id) == len(rows), "Duplicate run IDs")
    expected = expected_run_ids(paper_output)
    require(set(by_id) == expected, f"Expected all {len(expected)} protocol sections")
    for dataset, expected in expected_frames.items():
        selected = [r for r in rows if r["dataset"] == dataset]
        intervals = {(int(r["start_frame"]), int(r["frame_count"])) for r in selected}
        require(len(intervals) == 1, f"Inconsistent {dataset} intervals")
        start, count = next(iter(intervals))
        require(count > 0, f"Empty {dataset} interval")
        if expected is not None:
            require(count == expected, f"{dataset}: expected {expected} frames, found {count}")
        for r in selected:
            require(r["status"] == "ok", f"Run not complete: {r['run_id']}")
            require(int(r["frame_end"]) == start + count - 1, f"Invalid interval: {r['run_id']}")
            require(int(r["vertices"]) > 0 and int(r["faces"]) > 0, f"Empty mesh: {r['run_id']}")
    return by_id


def check_timings(root: Path, runs: dict[str, dict[str, str]], repetitions: tuple[int, int]) -> int:
    samples = csv_rows(root, "run_timings.csv")
    tables = csv_rows(root, "throughput_stats.csv")
    stats = {r["run_id"]: r for r in tables}
    throughput = {k: r for k, r in runs.items() if r["run_kind"] == "throughput"}
    require(len(tables) == 6 and set(stats) == set(throughput), "Expected six throughput statistics rows")
    count = 0
    for run_id, run in throughput.items():
        raw = [r for r in samples if r["run_id"] == run_id]
        measured = int(run["measured_runs"])
        require((int(run["warmup_runs"]), measured) == repetitions, f"Unexpected repetitions: {run_id}")
        require(len(raw) == measured, f"Missing timing samples: {run_id}")
        require(sorted(int(r["run_index"]) for r in raw) == list(range(measured)), f"Invalid repetition indices: {run_id}")
        values = [float(r["call_time_ms"]) for r in raw]
        require(all(math.isfinite(v) and v > 0 for v in values), f"Invalid timings: {run_id}")
        derived = summarize(values, int(run["frame_count"]))
        for key, value in derived.items():
            if key in stats[run_id] and key != "samples_ms":
                require(math.isclose(float(stats[run_id][key]), float(value), rel_tol=1e-9, abs_tol=1e-9),
                        f"Statistics disagree with samples: {run_id}/{key}")
        count += len(raw)
    return count


def check_memory(root: Path, runs: dict[str, dict[str, str]]) -> None:
    for run_id, run in runs.items():
        if run["run_kind"] != "memory_coarse":
            continue
        require(int(run["cpu_max_rss_bytes"]) > 0, f"Missing CPU peak: {run_id}")
        samples = csv_rows(root, f"memory/{run_id}.gpu.csv")
        require(all(r["pid"] and r["sampler_backend"] == "nvml-process-tree" for r in samples),
                f"Invalid GPU process attribution: {run_id}")
        peak = max(float(r["memory_used_mib"]) for r in samples)
        require(peak > 0 and math.isclose(peak, float(run["gpu_max_memory_mib"])), f"Missing/inconsistent GPU peak: {run_id}")


def check_quality(root: Path, variants=VARIANTS) -> None:
    rows = csv_rows(root, "quality.csv")
    require(len(rows) == len(variants) and {r["variant"] for r in rows} == set(variants), "Missing or unexpected quality evaluations")
    for row in rows:
        require(row["status"] == "ok", f"Quality not complete: {row['variant']}")
        require(math.isclose(float(row["tau_m"]), 0.1) and math.isclose(float(row["voxel_size_m"]), 0.05), "Quality protocol mismatch")
        require(int(row["sample_points"]) == 6_553_600, "Quality sample count mismatch")
        require(bool(row["evaluator_commit"]), "Missing evaluator revision")
        precision, recall, f1 = (float(row[k]) for k in ("precision", "recall", "f1"))
        require(all(math.isfinite(v) and 0 <= v <= 1 for v in (precision, recall, f1)), "Invalid quality scores")
        expected = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        require(math.isclose(f1, expected, abs_tol=1e-9), "Quality F1 is inconsistent")
        directory = root / "quality/maicity_tanks_and_temples" / row["variant"]
        metrics = json.loads((directory / "metrics.json").read_text())
        require(metrics["evaluator_repository"]["commit"] == row["evaluator_commit"], "Evaluator revisions disagree")
        for key in ("precision", "recall", "f1", "tau_m", "voxel_size_m", "sample_points"):
            require(math.isclose(float(metrics[key]), float(row[key]), abs_tol=1e-9), f"Quality tables disagree: {key}")
        for name in ("__.precision.ply", "__.recall.ply", "__.prf_tau_plotstr.txt"):
            require((directory / name).stat().st_size > 0, f"Missing quality artifact: {name}")


def validate_bundle(root: Path, args) -> dict:
    metadata = json.loads((root / "metadata.json").read_text())
    require(bool(metadata.get("finished_at")), "Protocol has not finished")
    for key in ("git", "source_git"):
        require(bool(metadata[key]["commit"]) and not metadata[key]["status"], f"Missing or dirty revision: {key}")
    paper_output = metadata["arguments"].get("paper_output", False)
    runs = check_runs(root, {"kitti": args.expected_kitti_frames, "maicity": args.expected_maicity_frames}, paper_output)
    timing_count = check_timings(root, runs, (args.expected_warmups, args.expected_runs))
    check_memory(root, runs)
    names = ["frame_metrics.csv", "stage_timings.csv", "memory_stages.csv"]
    if not paper_output:
        names.append("scheduler_timeline.csv")
    for name in names:
        rows = csv_rows(root, name)
        require(all(r["run_id"] in runs for r in rows), f"Unrecognized runs in {name}")
        if name == "frame_metrics.csv":
            for run_id, run in runs.items():
                frames = [int(r["frame"]) for r in rows if r["run_id"] == run_id]
                start, count = int(run["start_frame"]), int(run["frame_count"])
                require(sorted(frames) == list(range(start, start + count)), f"Incomplete frame metrics: {run_id}")
    if not args.skip_quality:
        check_quality(root)
    sensitivity_checked = False
    if metadata["arguments"].get("include_sensitivity"):
        require(not args.skip_quality, "The automatic sensitivity campaign requires quality validation")
        check_quality(root / "sensitivity", (VARIANTS[-1],))
        from paper_results.sensitivity import validate
        sensitivity_checked = validate(root, metadata)
    from paper_results.runtime import records
    additional = records(root, metadata)
    return {
        "status": "passed", "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_commit": metadata["source_git"]["commit"], "experiments_commit": metadata["git"]["commit"],
        "protocol_sections": len(runs), "throughput_samples": timing_count,
        "frame_counts": {d: int(runs[f"{d}_scheduler_none_throughput"]["frame_count"]) for d in ("kitti", "maicity")},
        "quality_checked": not args.skip_quality,
        "sensitivity_checked": sensitivity_checked,
        "runtime_sequences": [r["sequence"] for r in additional],
        "additional_runtime_samples": len(additional) * metadata["arguments"]["runs"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--expected-kitti-frames", type=int)
    parser.add_argument("--expected-maicity-frames", type=int)
    parser.add_argument("--expected-warmups", type=int, default=3)
    parser.add_argument("--expected-runs", type=int, default=10)
    parser.add_argument("--skip-quality", action="store_true", help="Check meshing measurements only.")
    parser.add_argument("--output", type=Path, help="Optional JSON verification report.")
    args = parser.parse_args()
    root = args.bundle.expanduser().resolve()
    if (root / "provenance.json").is_file() or root.is_file():
        from paper_results.bundle import open_bundle
        if root.is_dir():
            provenance = json.loads((root / "provenance.json").read_text())
            args.skip_quality = args.skip_quality or not provenance["verification"]["quality_checked"]
        with open_bundle(root) as raw:
            if root.is_file():
                args.skip_quality = args.skip_quality or json.loads((raw / "metadata.json").read_text())["arguments"].get("skip_quality", False)
            report = validate_bundle(raw, args)
    else:
        report = validate_bundle(root, args)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(f"check_protocol.py: {error}", file=sys.stderr)
        raise SystemExit(1)
