"""Shared data and artifact descriptions for a paper result bundle."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

DATASETS = ("maicity", "kitti")
VARIANTS = ("scheduler_none", "scheduler_pre_scan", "reference_pre_scan_polyline")
LABELS = dict(zip(VARIANTS, ("Sequential", "Early preparation", "Boundary-assisted")))
DATASET_LABELS = {"maicity": "Mai City", "kitti": "KITTI"}
COMPARISON_METHODS = ("RIMBA", "VDBFusion", "PUMA", "SLAMesh", "ImMesh", "CAD-Mesher")
WORKLOADS = {("Mai City", "01"): 100, ("KITTI", "03"): 801, ("KITTI", "05"): 2761,
             ("KITTI", "06"): 1101, ("KITTI", "07"): 1101, ("KITTI", "10"): 1201}
SECTIONS = {
    "geometric_quality": "Geometric quality",
    "computational_performance": "Computational performance",
    "scheduling_ablation": "Scheduling ablation",
}
CATALOG = {
    "table_quality": ("geometric_quality", "tab:evaluation-geometric-quality", "Geometric quality comparison", "table"),
    "figure_error_maps": ("geometric_quality", "fig:evaluation-quality-maps", "Spatial precision and recall", "figure"),
    "figure_qualitative": ("geometric_quality", "fig:evaluation-qualitative", "Matched qualitative views", "figure"),
    "table_runtime": ("computational_performance", "tab:evaluation-external-performance", "Cross-method performance", "table"),
    "figure_frame_time": ("computational_performance", "fig:evaluation-frame-time", "Temporal scalability", "figure"),
    "figure_stage_profile": ("computational_performance", "fig:evaluation-stage-profile", "Stage attribution", "figure"),
    "table_memory": ("computational_performance", "tab:evaluation-memory", "Peak sequential memory", "table"),
    "figure_memory": ("computational_performance", "fig:evaluation-memory", "Memory growth", "figure"),
    "figure_memory_breakdown": ("computational_performance", "fig:evaluation-memory-breakdown", "Final-frame memory breakdown", "figure"),
    "table_scheduling": ("scheduling_ablation", "tab:evaluation-scheduler-ablation", "Scheduling ablation", "table"),
    "table_output_effect": ("scheduling_ablation", "tab:evaluation-output-effect", "Scheduling effect on the reconstruction", "table"),
}


def read_csv(root: Path, name: str) -> list[dict[str, str]]:
    path = root / name
    if not path.is_file():
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Refusing an empty paper table: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        columns = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def one(rows, description: str) -> dict:
    rows = list(rows)
    if len(rows) != 1:
        raise ValueError(f"Expected one {description}, found {len(rows)}")
    return rows[0]


def number(row: dict, field: str) -> float:
    import math
    value = float(row[field])
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {field}")
    return value


class Publication:
    """Files and availability for one export, independent of the measurement run."""

    def __init__(self, output: Path, source: Path):
        self.output = output
        self.source = source
        self.metadata = json.loads((source / "metadata.json").read_text())
        self.verification = {}
        self.items = {}

    def item(self, key: str, status: str = "complete", note: str = "") -> dict:
        section, label, title, kind = CATALOG[key]
        item = {"id": key, "section": section, "paper_label": label, "title": title,
                "kind": kind, "status": status, "note": note, "files": []}
        self.items[key] = item
        return item

    def path(self, key: str, suffix: str) -> Path:
        directory = self.output / ("data" if suffix == "csv" else "figures")
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{key}.{suffix}"

    def register(self, key: str, path: Path) -> None:
        self.items[key]["files"].append(str(path.relative_to(self.output)))

    def data(self, key: str, rows: list[dict], name: str | None = None) -> Path:
        path = self.path(key, "csv") if name is None else self.path(key, "csv").with_name(name)
        write_csv(path, rows)
        self.register(key, path)
        return path
