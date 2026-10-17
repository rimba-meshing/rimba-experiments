"""Additional KITTI workloads used only in the cross-method timing table."""
from __future__ import annotations

import math
from pathlib import Path

from .common import WORKLOADS, VARIANTS, number, one, read_csv

EXTRA_KITTI = {sequence: count for (dataset, sequence), count in WORKLOADS.items() if dataset == "KITTI" and sequence != "07"}


def measure(args, binary: Path) -> None:
    # Reuse the protocol's command construction and raw timing parser exactly.
    try:
        import run_paper_protocol as protocol
    except ModuleNotFoundError:
        from tools import run_paper_protocol as protocol
    for sequence, full_count in EXTRA_KITTI.items():
        count = args.runtime_frame_count or full_count
        indices = protocol.numeric_frame_indices(args.kitti_dataset, sequence)
        if len(indices) < count or indices[0] != 0:
            raise ValueError(f"KITTI {sequence} needs frames 0..{count - 1}")
        spec = {"kind": "kitti", "dataset": str(args.kitti_dataset), "sequence": sequence, "start": 0, "count": count}
        directory = args.output / "runtime_sequences" / sequence
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Runtime comparison: KITTI {sequence}, {count} frames", flush=True)
        row, summary, _, _, _, _ = protocol.run_application(args, spec, VARIANTS[-1], "throughput", binary, directory, keep_mesh=False)
        row["status"] = "planned" if args.dry_run else "ok"
        timings = protocol.run_timing_rows_for(row, summary)
        protocol.write_csv(directory / "results.csv", [row])
        protocol.write_csv(directory / "run_timings.csv", timings)
        protocol.write_throughput_statistics([row], timings, directory)


def records(source: Path, metadata: dict) -> list[dict]:
    arguments = metadata["arguments"]
    if not arguments.get("include_runtime_sequences"):
        return []
    try:
        from benchmark_statistics import summarize
    except ModuleNotFoundError:
        from tools.benchmark_statistics import summarize
    output = []
    for sequence, full_count in EXTRA_KITTI.items():
        directory = source / "runtime_sequences" / sequence
        row = one(read_csv(directory, "results.csv"), f"KITTI {sequence} timing pass")
        count = arguments.get("runtime_frame_count") or full_count
        if row["status"] != "ok" or row["variant"] != VARIANTS[-1] or row["dataset"] != "kitti" or row["run_kind"] != "throughput":
            raise ValueError(f"Invalid runtime configuration: KITTI {sequence}")
        if (row["sequence"], int(row["start_frame"]), int(row["frame_count"]), int(row["frame_end"])) != (sequence, 0, count, count - 1):
            raise ValueError(f"Unexpected runtime interval: KITTI {sequence}")
        if int(row["vertices"]) <= 0 or int(row["faces"]) <= 0:
            raise ValueError(f"Empty runtime reconstruction: KITTI {sequence}")
        if (int(row["warmup_runs"]), int(row["measured_runs"])) != (arguments["warmup_runs"], arguments["runs"]):
            raise ValueError(f"Unexpected runtime repetitions: KITTI {sequence}")
        samples = read_csv(directory, "run_timings.csv")
        if sorted(int(r["run_index"]) for r in samples) != list(range(arguments["runs"])):
            raise ValueError(f"Incomplete runtime samples: KITTI {sequence}")
        identity = ("run_id", "dataset", "sequence", "start_frame", "frame_count", "variant")
        if any(any(r[key] != row[key] for key in identity) for r in samples):
            raise ValueError(f"Runtime sample identity mismatch: KITTI {sequence}")
        values = [number(r, "call_time_ms") for r in samples]
        if any(v <= 0 for v in values):
            raise ValueError("Non-positive timing sample")
        derived = summarize(values, count)
        stats = one(read_csv(directory, "throughput_stats.csv"), f"KITTI {sequence} timing statistics")
        if any(stats[key] != row[key] for key in ("run_id", "dataset", "sequence", "variant")):
            raise ValueError(f"Runtime statistic identity mismatch: KITTI {sequence}")
        for field, value in derived.items():
            if field in stats and field != "samples_ms" and not math.isclose(float(stats[field]), float(value), rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(f"Runtime statistics disagree: KITTI {sequence}/{field}")
        output.append({"dataset": "KITTI", "sequence": sequence, "method": "RIMBA", "frames": count,
                       "time_ms_per_frame": derived["mean_ms_per_frame"],
                       "ci95_half_width_ms_per_frame": derived["ci95_half_width_ms_per_frame"], "source": "this run"})
    return output
