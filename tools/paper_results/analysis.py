"""Derive manuscript measurements without changing their statistical meaning."""
from __future__ import annotations

import math
from .categories import stage_categories, device_memory_group
from .common import DATASETS, VARIANTS, LABELS, DATASET_LABELS, read_csv, one, number


def throughput(source):
    rows = read_csv(source, "results.csv")
    stats = {r["run_id"]: r for r in read_csv(source, "throughput_stats.csv")}
    quality = {r.get("variant"): r for r in read_csv(source, "quality.csv") if r.get("status") == "ok"}
    values = []
    for dataset in DATASETS:
        baseline = number(stats[f"{dataset}_scheduler_none_throughput"], "mean_ms_per_frame")
        for variant in VARIANTS:
            run_id = f"{dataset}_{variant}_throughput"
            run = one((r for r in rows if r["run_id"] == run_id), run_id)
            stat = stats[run_id]
            memory = one((r for r in rows if r["run_id"] == f"{dataset}_{variant}_memory_coarse"), "memory pass")
            values.append({
                "dataset": DATASET_LABELS[dataset], "sequence": run["sequence"], "variant": variant,
                "configuration": LABELS[variant], "frames": int(run["frame_count"]),
                "time_ms_per_frame": number(stat, "mean_ms_per_frame"),
                "ci95_half_width_ms_per_frame": number(stat, "ci95_half_width_ms_per_frame"),
                "reduction_percent": 100 * (baseline - number(stat, "mean_ms_per_frame")) / baseline,
                "host_rss_gib": number(memory, "cpu_max_rss_bytes") / 2**30,
                "device_vram_gib": number(memory, "gpu_max_memory_mib") / 1024,
                "vertices": int(run["vertices"]), "faces": int(run["faces"]),
                "f1_percent": 100 * number(quality[variant], "f1") if dataset == "maicity" and variant in quality else "",
            })
    return values


def frame_profiles(source):
    rows = [r for r in read_csv(source, "frame_metrics.csv") if r["run_kind"] == "throughput"]
    output = {}
    for dataset in DATASETS:
        selected = [r for r in rows if r["dataset"] == dataset]
        by_variant = {v: {int(r["frame"]): number(r, "frame_ms") for r in selected if r["variant"] == v} for v in VARIANTS}
        frames = sorted(by_variant[VARIANTS[0]])
        if not frames or any(set(by_variant[v]) != set(frames) for v in VARIANTS):
            raise ValueError(f"Mismatched frame positions: {dataset}")
        output[dataset] = [{"frame": f, "none": by_variant[VARIANTS[0]][f],
                            "prescan": by_variant[VARIANTS[1]][f], "polyline": by_variant[VARIANTS[2]][f]} for f in frames]
    return output


def stage_profiles(source):
    categories = stage_categories()
    flattened = [s for stages in categories.values() for s in stages]
    if len(flattened) != len(set(flattened)):
        raise ValueError("Overlapping timer categories")
    rows = [r for r in read_csv(source, "stage_timings.csv") if r["run_kind"] == "stage_sequential"]
    unknown = {r["stage"] for r in rows if r["stage"].startswith(("scan.", "mesh.")) and r["stage"] not in flattened}
    if unknown:
        raise ValueError(f"Unaudited scan/mesh timer scopes: {sorted(unknown)}")
    results = read_csv(source, "results.csv")
    output = []
    for index, dataset in enumerate(DATASETS):
        selected = [r for r in rows if r["dataset"] == dataset]
        frames = len({r["frame"] for r in selected})
        if not frames:
            raise ValueError(f"Missing sequential stage samples: {dataset}")
        values = {key: sum(number(r, "milliseconds") for r in selected if r["stage"] in names) / frames for key, names in categories.items()}
        run = one((r for r in results if r["dataset"] == dataset and r["run_kind"] == "stage_sequential"), "sequential timer pass")
        total = number(run, "ms_per_frame")
        residual = total - sum(values.values())
        if residual < -1e-6:
            raise ValueError(f"Selected timer scopes exceed total: {dataset}")
        output.append({"x": index, "dataset": DATASET_LABELS[dataset], **values, "other": max(0, residual), "total_ms": total})
    return output


def memory_breakdown(row):
    groups = dict.fromkeys(("gpu_mesh", "gpu_accumulated_depth", "gpu_range_meshing", "gpu_boundary",
                            "host_mesh", "host_topology", "host_auxiliary"), 0.0)
    for column, raw in row.items():
        if not column.endswith("_live_bytes") or "." not in column:
            continue
        value = float(raw or 0)
        if column.startswith(("main_cuda.", "prefetch_cuda.")):
            groups[device_memory_group(column.split(".", 1)[1].removesuffix("_live_bytes"))] += value
        elif column.startswith("host.stitch."):
            field = column.split(".", 2)[2].removesuffix("_live_bytes")
            groups["host_mesh" if field in {"host_vertices_global", "host_vertex_normal_sums_global"} else "host_topology"] += value
        elif column.startswith(("host.main.", "host.prefetch.", "host.accumulated_")):
            groups["host_auxiliary"] += value
    for prefix, field in (("gpu_", "cuda_live_bytes"), ("host_", "host_live_bytes")):
        if not math.isclose(sum(v for k, v in groups.items() if k.startswith(prefix)), number(row, field), rel_tol=0, abs_tol=1):
            raise ValueError(f"Allocation groups do not sum to {field}")
    return {k: v / 2**30 for k, v in groups.items()}


def memory_profiles(source):
    rows = read_csv(source, "memory_stages.csv")
    results = read_csv(source, "results.csv")
    profiles, summaries, breakdowns = {}, [], []
    fields = ("cpu_rss", "host_live", "host_capacity", "cuda_live", "cuda_capacity")
    for index, dataset in enumerate(DATASETS):
        selected = [r for r in rows if r["dataset"] == dataset and r["variant"] == "scheduler_none" and r["pass_kind"] == "measured"]
        ends = sorted((r for r in selected if r["stage"] == "frame_end"), key=lambda r: int(r["frame"]))
        if not ends:
            raise ValueError(f"Missing measured frame-end memory: {dataset}")
        profiles[dataset] = [{"frame": int(r["frame"]), **{f: number(r, f + "_bytes") / 2**30 for f in fields}} for r in ends]
        detailed = one((r for r in results if r["dataset"] == dataset and r["run_kind"] == "memory_detailed"), "detailed memory pass")
        coarse = one((r for r in results if r["dataset"] == dataset and r["run_kind"] == "memory_coarse" and r["variant"] == "scheduler_none"), "sequential process memory")
        summaries.append({"dataset": DATASET_LABELS[dataset], "sequence": detailed["sequence"],
                          **{f + "_gib": max(number(r, f + "_bytes") for r in selected) / 2**30 for f in fields[1:]},
                          "host_rss_gib": number(detailed, "cpu_max_rss_bytes") / 2**30,
                          "device_vram_gib": number(coarse, "gpu_max_memory_mib") / 1024})
        breakdowns.append({"x": index, "dataset": DATASET_LABELS[dataset], **memory_breakdown(ends[-1])})
    return profiles, summaries, breakdowns
