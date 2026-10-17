"""Extract the native means used by the paper's comparison protocol."""
from __future__ import annotations

import csv
import math
from pathlib import Path
import re
import statistics

SCOPES = {
    "vdbfusion": "native TSDF integration",
    "puma": "native incremental mapping compute",
    "slamesh": "native fixed-pose mapping time_cost",
    "immesh": "native asynchronous reconstruction step_total_ms",
    "cad_mesher": "native time_cost update vector without its initial zero",
}


def accepted(method: str, count: int, expected: int) -> bool:
    return (count == expected or (method in {"puma", "immesh"} and 0 < expected - count <= 2)
            or (method == "cad_mesher" and 0 < count <= expected))


def summary(method: str, values: list[float], expected: int, source: str) -> dict:
    if not values or not all(math.isfinite(v) and v >= 0 for v in values) or statistics.fmean(values) <= 0:
        raise ValueError(f"Missing or invalid native timing: {method}/{source}")
    if not accepted(method, len(values), expected):
        raise ValueError(f"Unexpected native timing count for {method}: {len(values)} of {expected}")
    return {"time_ms_per_frame": statistics.fmean(values), "median_ms": statistics.median(values),
            "native_frame_count": len(values), "native_trace_complete": len(values) == expected,
            "scope": SCOPES[method], "source": source, "policy": "paper native mean"}


def from_csv(path: Path, field: str, method: str, expected: int) -> dict:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return summary(method, [float(r[field]) for r in rows], expected, path.name)


def scalar(text: str, label: str) -> float:
    match = re.search(rf"^\s*{re.escape(label)}:\s*([-+0-9.eE]+)\s*$", text, re.MULTILINE)
    if not match or not math.isfinite(float(match[1])):
        raise ValueError(f"Missing native report field: {label}")
    return float(match[1])


def vector(text: str, label: str) -> list[float]:
    match = re.search(rf"^[ \t]*{re.escape(label)}:[^\n]*\n(.*?)(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return [float(v) for v in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", match[1])]


def from_report(path: Path, method: str, expected: int) -> dict:
    text = path.read_text(errors="replace")
    steps = int(scalar(text, "step"))
    if method == "cad_mesher":
        values = vector(text, "time_cost")
        if values and abs(values[0]) <= 1e-9:
            values = values[1:]
        if len(values) != steps:
            raise ValueError("CAD timing vector and step counter disagree")
        return summary(method, values, expected, path.name)
    mean = scalar(text, "time_cost")
    if steps != expected or mean <= 0:
        raise ValueError("SLAMesh native report is incomplete")
    return {"time_ms_per_frame": mean, "native_frame_count": steps, "native_trace_complete": True,
            "scope": SCOPES[method], "source": path.name, "policy": "paper native mean"}
