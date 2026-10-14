#!/usr/bin/env python3
"""Create tables and plots from a checked protocol bundle, without measuring."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


VARIANTS = ("scheduler_none", "scheduler_pre_scan", "reference_pre_scan_polyline")
LABELS = ("Sequential / no blocker", "Pre-scan / no blocker", "Pre-scan / polyline")
COLORS = ("#64748b", "#0891b2", "#b45309")


def rows(root: Path, name: str) -> list[dict[str, str]]:
    with (root / name).open(newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers: tuple[str, ...], records: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(row) + " |" for row in records), ""]


def ordered(data: list[dict[str, str]], dataset: str) -> list[dict[str, str]]:
    selected = {row["variant"]: row for row in data if row["dataset"] == dataset}
    return [selected[variant] for variant in VARIANTS]


def save_figure(figure, directory: Path, name: str) -> None:
    figure.tight_layout()
    for suffix in ("png", "pdf"):
        figure.savefig(directory / f"{name}.{suffix}", dpi=200, bbox_inches="tight")


def throughput_plot(plt, data: list[dict[str, str]], output: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    for axis, dataset in zip(axes, ("kitti", "maicity")):
        selected = ordered(data, dataset)
        means = [float(r["mean_ms_per_frame"]) for r in selected]
        errors = [float(r["ci95_half_width_ms_per_frame"]) for r in selected]
        axis.bar(range(3), means, yerr=errors, capsize=4, color=COLORS)
        axis.set_xticks(range(3), ("None", "Pre-scan", "Pre-scan\n+ polyline"))
        axis.set_ylabel("Mean time per frame (ms)")
        axis.set_title(f"{dataset.upper()} — 95% confidence intervals")
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    save_figure(figure, output, "throughput")
    plt.close(figure)


def memory_plot(plt, data: list[dict[str, str]], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(10, 7))
    for column, dataset in enumerate(("kitti", "maicity")):
        selected = ordered(data, dataset)
        for row_index, key in enumerate(("cpu_max_rss_bytes", "gpu_max_memory_mib")):
            values = [float(r[key]) / (1024 ** 2 if row_index == 0 else 1) for r in selected]
            axis = axes[row_index, column]
            axis.bar(range(3), values, color=COLORS)
            axis.set_xticks(range(3), ("None", "Pre-scan", "Pre-scan\n+ polyline"))
            axis.set_title(dataset.upper())
            axis.set_ylabel("CPU peak RSS (MiB)" if row_index == 0 else "Process GPU peak (MiB)")
            axis.grid(axis="y", alpha=0.2)
            axis.set_axisbelow(True)
    save_figure(figure, output, "memory")
    plt.close(figure)


def quality_plot(plt, data: list[dict[str, str]], output: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 4))
    for index, row in enumerate(ordered(data, "maicity")):
        positions = [metric + (index - 1) * 0.24 for metric in range(3)]
        axis.bar(positions, [float(row[k]) for k in ("precision", "recall", "f1")],
                 width=0.23, color=COLORS[index], label=LABELS[index])
    axis.set_xticks(range(3), ("Precision", "Recall", "F1"))
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("Score (0–1)")
    axis.set_title("MaiCity geometric quality")
    axis.legend(loc="lower left", fontsize=9)
    save_figure(figure, output, "quality")
    plt.close(figure)


def make_report(root: Path, metadata: dict, verification: dict) -> list[str]:
    full = verification["frame_counts"] == {"kitti": 1101, "maicity": 100} and all(
        row["start_frame"] == "0" and row["sequence"] == {"kitti": "07", "maicity": "01"}[row["dataset"]]
        for row in rows(root, "results.csv")
    )
    lines = ["# RIMBA results", "", "Full sequence protocol." if full else "**Diagnostic interval; not a full-sequence paper run.**", "",
             f"Source revision: `{verification['source_commit']}`.  ",
             f"Experiments revision: `{verification['experiments_commit']}`.  ",
             f"Sections checked: {verification['protocol_sections']}; measured throughput samples: {verification['throughput_samples']}.", "",
             "## Throughput", "", "Means and 95% Student-t confidence intervals use repeated full-interval meshing calls. FPS is 1000 divided by mean ms/frame.", ""]
    records = []
    for dataset in ("kitti", "maicity"):
        for label, row in zip(LABELS, ordered(rows(root, "throughput_stats.csv"), dataset)):
            mean = float(row["mean_ms_per_frame"])
            interval = f"{float(row['ci95_low_ms_per_frame']):.3f}–{float(row['ci95_high_ms_per_frame']):.3f}"
            records.append([dataset.upper(), row["frame_count"], label, f"{mean:.3f}", interval, f"{1000 / mean:.2f}"])
    lines += table(("Dataset", "Frames", "Variant", "ms/frame", "95% CI (ms/frame)", "FPS"), records)
    lines += ["![Throughput](throughput.png)", "", "## Peak process memory", "",
              "Separate measurement passes; CPU peak RSS and absolute NVML process-tree GPU peaks in MiB.", ""]
    memory = [r for r in rows(root, "results.csv") if r["run_kind"] == "memory_coarse"]
    records = []
    for dataset in ("kitti", "maicity"):
        for label, row in zip(LABELS, ordered(memory, dataset)):
            records.append([dataset.upper(), label, f"{float(row['cpu_max_rss_bytes']) / 1024 ** 2:.1f}", f"{float(row['gpu_max_memory_mib']):.1f}"])
    lines += table(("Dataset", "Variant", "CPU MiB", "GPU MiB"), records)
    lines += ["![Memory](memory.png)", "", "## Geometric quality", ""]
    if verification["quality_checked"]:
        records = [[label, *(f"{float(row[k]):.6f}" for k in ("precision", "recall", "f1"))]
                   for label, row in zip(LABELS, ordered(rows(root, "quality.csv"), "maicity"))]
        lines += table(("Variant", "Precision", "Recall", "F1"), records)
        lines += ["MaiCity sequence 01 against the independent reference: τ = 0.10 m, voxel size = 0.05 m, 6,553,600 mesh samples. Random sampling can cause small differences.", "",
                  "![Quality](quality.png)", ""]
    else:
        lines += ["**Quality evaluation was omitted; this report covers meshing measurements only.**", ""]
    lines += ["## Provenance and other outputs", "", f"Platform: {metadata['platform']}.  ",
              f"Run started: {metadata['started_at']}; finished: {metadata['finished_at']}.", "",
              "GPU snapshot:", "", "```text", *metadata.get("gpu_before", []), "```", "",
              "- [Verification](verification.json)", "- [Run manifest](../metadata.json)",
              "- [Throughput comparisons](../throughput_comparisons.csv)", "- [Stage summaries](../stage_summary.csv)",
              "- [Memory instrumentation](../memory_stages.csv)", "- [Scheduler timelines](../scheduler_timeline.csv)",
              "- [Generated meshes](../meshes/)", "- [Commands](../commands/)", "- [Logs](../logs/)", "",
              "Plots are also available as PDFs. Runtime and memory depend on hardware and load. This run covers RIMBA configurations; external-method comparisons require their own reconstructions and measurements.", ""]
    if (root / "environment.json").is_file():
        lines += ["- [Toolchain and Python packages](../environment.json)", ""]
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    root = args.bundle.expanduser().resolve()
    output = root / "report"
    verification = json.loads((output / "verification.json").read_text())
    metadata = json.loads((root / "metadata.json").read_text())
    if verification["status"] != "passed" or any(
        verification[key] != metadata[field]["commit"]
        for key, field in (("source_commit", "source_git"), ("experiments_commit", "git"))
    ):
        raise ValueError("Validate this bundle with check_protocol.py before generating its report.")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    throughput_plot(plt, rows(root, "throughput_stats.csv"), output)
    memory_plot(plt, [r for r in rows(root, "results.csv") if r["run_kind"] == "memory_coarse"], output)
    if verification["quality_checked"]:
        quality_plot(plt, rows(root, "quality.csv"), output)
    (output / "README.md").write_text("\n".join(make_report(root, metadata, verification)), encoding="utf-8")
    print(output / "README.md")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(f"report_protocol.py: {error}", file=sys.stderr)
        raise SystemExit(1)
