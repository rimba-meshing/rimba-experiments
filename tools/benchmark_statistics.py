#!/usr/bin/env python3
"""Statistics for repeated in-process throughput benchmark runs.

The executable reports one ``Measured run N call time`` line per measured
run.  This module deliberately treats those runs as the statistical samples;
individual frames are not treated as independent repetitions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


_RUN_TIME_RE = re.compile(
    r"^Measured run\s+(\d+)(?:\s+call time):\s+([\d.eE+-]+)\s+ms$"
)

# Two-sided 95% Student-t critical values.  The benchmark normally uses ten
# measured runs (df=9), but keeping the small table makes the helper useful for
# smoke tests as well.  The final entries cover larger campaigns.
_T95 = {
    1: 12.7062047364,
    2: 4.30265272975,
    3: 3.18244630528,
    4: 2.77644510520,
    5: 2.57058183564,
    6: 2.44691185114,
    7: 2.36462425101,
    8: 2.30600413503,
    9: 2.26215716285,
    10: 2.22813885196,
    11: 2.20098516008,
    12: 2.17881282967,
    13: 2.16036865646,
    14: 2.14478668792,
    15: 2.13144954556,
    16: 2.11990529922,
    17: 2.10981557783,
    18: 2.10092204024,
    19: 2.09302405441,
    20: 2.08596344727,
    21: 2.07961384473,
    22: 2.07387306790,
    23: 2.06865761042,
    24: 2.06389856163,
    25: 2.05953855275,
    26: 2.05552943864,
    27: 2.05183051648,
    28: 2.04840714180,
    29: 2.04522964213,
    30: 2.04227245630,
    40: 2.02107539031,
    60: 2.00029782106,
    120: 1.97993040505,
}


def parse_run_timings(text: str) -> list[float]:
    """Return raw measured call times in the order reported by the binary."""

    samples: dict[int, float] = {}
    for line in text.splitlines():
        match = _RUN_TIME_RE.match(line.strip())
        if match:
            samples[int(match.group(1))] = float(match.group(2))
    return [samples[index] for index in sorted(samples)]


def _critical_value(degrees_of_freedom: int) -> float:
    if degrees_of_freedom <= 0:
        return 0.0
    if degrees_of_freedom in _T95:
        return _T95[degrees_of_freedom]
    larger = [value for value in _T95 if value > degrees_of_freedom]
    if not larger:
        return 1.95996398454
    upper = min(larger)
    lower = max(value for value in _T95 if value < degrees_of_freedom)
    # Linear interpolation is only a fallback for uncommon sample counts;
    # the standard ten-run case uses the exact tabulated value above.
    return _T95[lower] + (_T95[upper] - _T95[lower]) * (
        (degrees_of_freedom - lower) / (upper - lower)
    )


def summarize(samples_ms: Iterable[float], frame_count: int) -> dict[str, Any]:
    """Summarize repeated total-call timings, including a 95% t interval."""

    samples = [float(value) for value in samples_ms]
    if not samples:
        raise ValueError("at least one measured run is required")
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    count = len(samples)
    mean_ms = sum(samples) / count
    if count > 1:
        variance = sum((value - mean_ms) ** 2 for value in samples) / (count - 1)
        std_ms = math.sqrt(variance)
    else:
        std_ms = 0.0
    mean_per_frame = mean_ms / frame_count
    std_per_frame = std_ms / frame_count
    critical = _critical_value(count - 1)
    half_width = critical * std_per_frame / math.sqrt(count) if count > 1 else 0.0
    return {
        "sample_count": count,
        "samples_ms": samples,
        "mean_ms": mean_ms,
        "std_ms": std_ms,
        "mean_ms_per_frame": mean_per_frame,
        "std_ms_per_frame": std_per_frame,
        "ci95_critical_t": critical,
        "ci95_half_width_ms_per_frame": half_width,
        "ci95_low_ms_per_frame": mean_per_frame - half_width,
        "ci95_high_ms_per_frame": mean_per_frame + half_width,
    }


def comparison_stats(
    baseline_samples_ms: Iterable[float],
    variant_samples_ms: Iterable[float],
    frame_count: int,
) -> dict[str, Any]:
    """Compare two independent repeated runs using Welch's mean-difference CI.

    The reduction interval is derived from that difference interval and the
    observed baseline mean.  It is intentionally labelled as a derived CI;
    it does not pretend that a sequence of frames provides paired samples.
    """

    baseline = summarize(baseline_samples_ms, frame_count)
    variant = summarize(variant_samples_ms, frame_count)
    n0 = baseline["sample_count"]
    n1 = variant["sample_count"]
    s0 = baseline["std_ms_per_frame"]
    s1 = variant["std_ms_per_frame"]
    se2 = s0 * s0 / n0 + s1 * s1 / n1
    se = math.sqrt(se2)
    if se == 0.0:
        degrees_of_freedom = 0
        critical = 0.0
    else:
        numerator = se2 * se2
        denominator = 0.0
        if n0 > 1:
            denominator += (s0 * s0 / n0) ** 2 / (n0 - 1)
        if n1 > 1:
            denominator += (s1 * s1 / n1) ** 2 / (n1 - 1)
        degrees_of_freedom = max(1, int(round(numerator / denominator))) if denominator else 1
        critical = _critical_value(degrees_of_freedom)
    difference = baseline["mean_ms_per_frame"] - variant["mean_ms_per_frame"]
    difference_half_width = critical * se
    baseline_mean = baseline["mean_ms_per_frame"]
    reduction_percent = 100.0 * difference / baseline_mean if baseline_mean else 0.0
    reduction_low = 100.0 * (difference - difference_half_width) / baseline_mean if baseline_mean else 0.0
    reduction_high = 100.0 * (difference + difference_half_width) / baseline_mean if baseline_mean else 0.0
    return {
        "baseline_mean_ms_per_frame": baseline_mean,
        "variant_mean_ms_per_frame": variant["mean_ms_per_frame"],
        "difference_ms_per_frame": difference,
        "difference_ci95_low_ms_per_frame": difference - difference_half_width,
        "difference_ci95_high_ms_per_frame": difference + difference_half_width,
        "reduction_percent": reduction_percent,
        "reduction_ci95_low_percent": reduction_low,
        "reduction_ci95_high_percent": reduction_high,
        "welch_degrees_of_freedom": degrees_of_freedom,
        "welch_ci95_critical_t": critical,
    }


def _write_run_csv(path: Path, summary: dict[str, Any], frame_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "run_index", "call_time_ms", "time_per_frame_ms"
        ))
        writer.writeheader()
        for index, value in enumerate(summary["samples_ms"]):
            writer.writerow({
                "run_index": index,
                "call_time_ms": value,
                "time_per_frame_ms": value / frame_count,
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--frame-count", type=int, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-csv", type=Path)
    args = parser.parse_args()
    summary = summarize(parse_run_timings(args.log.read_text(encoding="utf-8")), args.frame_count)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.output_csv:
        _write_run_csv(args.output_csv, summary, args.frame_count)
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
