"""CSV, LaTeX, and rendered tables with the manuscript's measurement scopes."""
from __future__ import annotations

from .common import COMPARISON_METHODS, WORKLOADS, VARIANTS, read_csv, number
from .latex import escape, render

HEADERS = {
    "dataset": "Dataset", "sequence": "Sequence", "configuration": "Configuration", "method": "Method",
    "frames": "Frames", "time_ms_per_frame": "Mean time / 95% CI (ms/frame)",
    "reduction_percent": "Reduction (%)", "host_rss_gib": "Process RSS (GiB)", "device_vram_gib": "VRAM (GiB)",
    "vertices": "Vertices", "faces": "Faces", "f1_percent": "F1-score (%)", "precision_percent": "Precision (%)",
    "recall_percent": "Recall (%)", "host_live_gib": "Host live (GiB)", "host_capacity_gib": "Host capacity (GiB)",
    "cuda_live_gib": "CUDA live (GiB)", "cuda_capacity_gib": "CUDA capacity (GiB)", "hardware": "Hardware",
    "max_triangle_edge_m": "Edge limit (m)",
}


def display(row: dict, field: str, latex: bool = False) -> str:
    value = row.get(field, "")
    if value == "":
        return "--"
    if field == "time_ms_per_frame" and row.get("ci95_half_width_ms_per_frame", "") != "":
        mean, ci = float(value), float(row["ci95_half_width_ms_per_frame"])
        return rf"${mean:.2f} \pm {ci:.2f}$" if latex else f"{mean:.2f} ± {ci:.2f}"
    if isinstance(value, int) or field in ("frames", "vertices", "faces"):
        text = f"{int(value):,}"
        return text.replace(",", r"\,") if latex else text
    if field.endswith("_percent"):
        return f"{float(value):.2f}"
    if isinstance(value, float) or field.endswith(("_gib", "_ms_per_frame", "_m")):
        return f"{float(value):.3f}"
    return escape(value) if latex else str(value)


def table(publication, key: str, records: list[dict], columns: tuple[str, ...]) -> None:
    publication.data(key, records)
    publication.items[key]["columns"] = list(columns)
    headers = [escape(HEADERS.get(c, c)) for c in columns]
    rows = [[display(row, c, True) for c in columns] for row in records]
    left = sum(c in {"dataset", "sequence", "configuration", "method"} for c in columns)
    render(publication, key, tabular(headers, rows, left))


def tabular(headers: list[str], rows: list[list[str]], left: int = 2) -> str:
    headers = [r"\shortstack{" + h.replace(" (", r"\\(").replace(" / ", r"\\") + "}" for h in headers]
    lines = [r"\begin{adjustbox}{max width=\linewidth}", r"\begin{tabular}{" + "l" * left + "r" * (len(headers) - left) + "}",
             r"\toprule", " & ".join(headers) + r" \\", r"\midrule"]
    lines += [" & ".join(row) + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}"]
    return "\n".join(lines)


def core_tables(publication, values: list[dict], memory: list[dict]) -> None:
    publication.item("table_memory", note="Sequential execution. Tracked storage, whole-process RSS, and NVML peaks have different scopes.")
    table(publication, "table_memory", memory, ("dataset", "sequence", "host_live_gib", "host_capacity_gib",
                                                "host_rss_gib", "cuda_live_gib", "cuda_capacity_gib", "device_vram_gib"))
    publication.item("table_scheduling", note="Means and Student-t 95% intervals use complete-call repetitions. Memory comes from separate passes.")
    table(publication, "table_scheduling", values, ("dataset", "configuration", "time_ms_per_frame",
                                                    "reduction_percent", "host_rss_gib", "device_vram_gib"))
    status = "complete" if publication.verification["quality_checked"] else "partial"
    note = "F1-score is evaluated on Mai City only." if status == "complete" else "Geometry counts only; geometric quality was omitted for this run."
    publication.item("table_output_effect", status, note)
    table(publication, "table_output_effect", values, ("dataset", "configuration", "vertices", "faces", "f1_percent"))


def runtime_table(publication, values: list[dict], supplied: list[dict]) -> None:
    records = []
    for row in values:
        if row["variant"] == VARIANTS[-1]:
            records.append({"dataset": row["dataset"], "sequence": row["sequence"], "method": "RIMBA",
                            "frames": row["frames"], "time_ms_per_frame": row["time_ms_per_frame"],
                            "ci95_half_width_ms_per_frame": row["ci95_half_width_ms_per_frame"], "source": "this run"})
    records.extend(supplied)
    hardware = next(iter(publication.metadata.get("gpu_before", [])), "not recorded").split(",")[0]
    for row in records:
        if row["source"] == "this run":
            row["hardware"] = hardware
    identities = {(r["dataset"], r["sequence"], r["method"]): int(r["frames"]) for r in records}
    if len(identities) != len(records):
        raise ValueError("Supplied runtime duplicates a measurement from this run")
    complete = all(identities.get((*workload, method)) == frames for workload, frames in WORKLOADS.items() for method in COMPARISON_METHODS)
    methods = [method for method in COMPARISON_METHODS if any(r["method"] == method for r in records)]
    methods += sorted({r["method"] for r in records} - set(methods))
    workloads = sorted({(r["dataset"], r["sequence"]) for r in records}, key=lambda w: (w[0] != "Mai City", w[1]))
    missing = [sequence for (dataset, sequence) in WORKLOADS if (dataset, sequence) not in workloads]
    note = "External-method results were not supplied." if methods == ["RIMBA"] else "Supplied measurements retain their sources and hardware descriptions in the CSV."
    if missing:
        note += " Missing KITTI sequences: " + ", ".join(missing) + "."
    publication.item("table_runtime", "supplied" if complete else "partial", note)
    publication.data("table_runtime", records)
    rows = []
    for dataset, sequence in workloads:
        selected = {r["method"]: r for r in records if (r["dataset"], r["sequence"]) == (dataset, sequence)}
        frames = {int(r["frames"]) for r in selected.values()}
        if len(frames) != 1:
            raise ValueError(f"Compared runtime methods use different intervals: {dataset} {sequence}")
        rows.append([escape(dataset), escape(sequence), display({"frames": frames.pop()}, "frames", True),
                     *[display(selected.get(method, {}), "time_ms_per_frame", True) for method in methods]])
    render(publication, "table_runtime", tabular(["Dataset", "Sequence", "Frames", *map(escape, methods)], rows))


def quality_table(publication, supplied: list[dict]) -> bool:
    quality = [r for r in read_csv(publication.source, "quality.csv") if r.get("status") == "ok"]
    if not publication.verification["quality_checked"]:
        publication.item("table_quality", "skipped", "Geometric quality was explicitly omitted for this run.")
        return False
    selected = next(r for r in quality if r["variant"] == VARIANTS[-1])
    records = [{"method": "RIMBA", "max_triangle_edge_m": 0.30, "precision_percent": 100 * number(selected, "precision"),
                "recall_percent": 100 * number(selected, "recall"), "f1_percent": 100 * number(selected, "f1"),
                "tau_m": number(selected, "tau_m"), "source": "this run"}, *supplied]
    methods = [r["method"] for r in records]
    if len(set(methods)) != len(methods):
        raise ValueError("Duplicate quality comparison methods")
    arguments = publication.metadata["arguments"]
    complete = set(COMPARISON_METHODS + ("RIMBA (0.55 m)",)).issubset(methods) and arguments["maicity_frame_count"] == 100 and arguments["maicity_start_frame"] == 0
    missing = sorted(set(COMPARISON_METHODS + ("RIMBA (0.55 m)",)) - set(methods))
    note = "Missing comparisons: " + ", ".join(missing) + "." if missing else ""
    if not complete and not missing:
        note = "Diagnostic interval; the paper comparison uses all 100 Mai City frames."
    publication.item("table_quality", "supplied" if complete else "partial", note)
    table(publication, "table_quality", records, ("method", "precision_percent", "recall_percent", "f1_percent"))
    return True
