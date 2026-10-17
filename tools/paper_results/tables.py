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
    if isinstance(value, float) or field.endswith(("_gib", "_percent", "_ms_per_frame", "_m")):
        return f"{float(value):.3f}"
    return escape(value) if latex else str(value)


def table(publication, key: str, records: list[dict], columns: tuple[str, ...]) -> None:
    publication.data(key, records)
    publication.items[key]["columns"] = list(columns)
    headers = [escape(HEADERS.get(c, c)) for c in columns]
    # Split long column headings rather than shrinking the whole table excessively.
    headers = [r"\shortstack{" + h.replace(" (", r"\\(").replace(" / ", r"\\") + "}" for h in headers]
    lines = [r"\centering\resizebox{\linewidth}{!}{", r"\begin{tabular}{" + "l" * len(columns) + "}",
             r"\toprule", " & ".join(headers) + r" \\", r"\midrule"]
    lines += [" & ".join(display(row, c, True) for c in columns) + r" \\" for row in records]
    lines += [r"\bottomrule", r"\end{tabular}", "}"]
    render(publication, key, "\n".join(lines))


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
    identities = {(r["dataset"], r["sequence"], r["method"]): int(r["frames"]) for r in records}
    if len(identities) != len(records):
        raise ValueError("Supplied runtime duplicates a measurement from this run")
    complete = all(identities.get((*workload, method)) == frames for workload, frames in WORKLOADS.items() for method in COMPARISON_METHODS)
    note = "RIMBA measurements from this run; supplied measurements retain source and hardware information in the CSV."
    if not complete:
        note += " The full paper comparison also needs external results and the additional KITTI workloads."
    publication.item("table_runtime", "supplied" if complete else "partial", note)
    table(publication, "table_runtime", records, ("dataset", "sequence", "method", "frames", "time_ms_per_frame"))


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
    note = "Generated RIMBA metrics and supplied cross-method measurements." if complete else "Reference configuration. The complete paper table also needs external methods and the edge-limit sensitivity experiment."
    publication.item("table_quality", "supplied" if complete else "partial", note)
    table(publication, "table_quality", records, ("method", "precision_percent", "recall_percent", "f1_percent"))
    return True
