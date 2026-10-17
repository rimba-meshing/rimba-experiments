"""Comparison measurements and matched views supplied to the report."""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil

from .common import DATASET_LABELS, read_csv, sha256
from .latex import render


def load(path: Path | None) -> dict:
    if path is None:
        return {}
    path = path.expanduser().resolve()
    data = json.loads(path.read_text())
    allowed = {"external_quality", "external_runtime", "sensitivity_results", "qualitative_pdf"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown paper inputs: {sorted(unknown)}")
    result = {}
    for key, value in data.items():
        if key == "qualitative_pdf":
            if not isinstance(value, dict) or not value.get("source"):
                raise ValueError("qualitative_pdf requires file and source fields")
            result[key] = {**value, "file": resolve(path.parent, value["file"])}
        else:
            result[key] = resolve(path.parent, value)
    result["manifest"] = {"path": str(path), "sha256": sha256(path)}
    return result


def resolve(parent: Path, value: str) -> Path:
    path = Path(value).expanduser()
    path = (parent / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.exists():
        raise ValueError(f"Paper input does not exist: {path}")
    return path


def external_rows(inputs: dict, kind: str) -> list[dict]:
    path = inputs.get("external_" + kind)
    if path is None:
        return []
    rows = read_csv(path.parent, path.name)
    if not rows:
        raise ValueError(f"Empty external {kind} input")
    output, identities = [], set()
    for row in rows:
        if not row.get("method") or not row.get("source"):
            raise ValueError(f"External {kind} requires method and source")
        if kind == "quality":
            scores = {key: float(row[key]) for key in ("precision", "recall", "f1")}
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in scores.values()):
                raise ValueError("External quality scores must be finite values in [0,1]")
            p, r = scores["precision"], scores["recall"]
            expected = 2 * p * r / (p + r) if p + r else 0
            if not math.isclose(scores["f1"], expected, abs_tol=1e-6):
                raise ValueError("External F1 disagrees with precision and recall")
            if not math.isclose(float(row["tau_m"]), 0.1) or not math.isclose(float(row["voxel_size_m"]), 0.05) or int(row["sample_points"]) != 6_553_600:
                raise ValueError("External quality must use the same evaluation protocol")
            record = {"method": row["method"], **{k + "_percent": 100 * v for k, v in scores.items()},
                      "tau_m": float(row["tau_m"]), "source": row["source"]}
            identity = row["method"]
        else:
            if not row.get("hardware"):
                raise ValueError("External runtime requires a hardware description")
            value = float(row["time_ms_per_frame"])
            if not math.isfinite(value) or value <= 0 or int(row["frames"]) <= 0:
                raise ValueError("Invalid external time or frame count")
            dataset = row["dataset"].lower().replace(" ", "")
            if dataset not in DATASET_LABELS:
                raise ValueError("External runtime dataset must be kitti or maicity")
            record = {"dataset": DATASET_LABELS[dataset], "sequence": row["sequence"].zfill(2), "method": row["method"],
                      "frames": int(row["frames"]), "time_ms_per_frame": value,
                      "ci95_half_width_ms_per_frame": "", "source": row["source"], "hardware": row["hardware"]}
            identity = (record["dataset"], record["sequence"], record["method"])
        for key in ("native_frame_count", "native_trace_complete", "timing_scope", "experiments_commit", "mesh_sha256", "reference_sha256", "evaluator_commit"):
            if key in row:
                record[key] = row[key]
        if identity in identities:
            raise ValueError(f"Duplicate external measurement: {identity}")
        identities.add(identity)
        output.append(record)
    return output


def qualitative(publication, inputs: dict) -> None:
    source = inputs.get("qualitative_pdf")
    if source is None:
        from .qualitative import compose
        compose(publication)
        return
    publication.item("figure_qualitative", "supplied", "Provided matched captures. Source: " + source["source"])
    pdf = publication.path("figure_qualitative", "pdf")
    shutil.copyfile(source["file"], pdf)
    publication.register("figure_qualitative", pdf)
    render(publication, "figure_qualitative", r"\includegraphics[width=\linewidth,height=.6\textheight,keepaspectratio]{figures/figure_qualitative.pdf}")
