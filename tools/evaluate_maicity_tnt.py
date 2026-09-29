#!/usr/bin/env python3
"""Evaluate one mesh with the RuanJY TanksAndTemples MaiCity protocol.

The fork's ``run.py`` retains the historical ``--traj-path`` CLI argument,
although the fork removed trajectory alignment.  This wrapper loads its
``run_evaluation`` function directly, making the no-trajectory protocol
explicit and avoiding a dummy trajectory path.

The protocol is fixed by the fork: tau = 0.10 m, 6,553,600 uniform samples
from the reconstructed triangle mesh, and 0.05 m voxel downsampling for both
clouds.  The reference must be an independently accumulated MaiCity point
cloud, normally made from sequence 02 while sequence 01 is the input run.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


TAU_METERS = 0.10
SAMPLE_POINTS = 6_553_600
VOXEL_SIZE_METERS = TAU_METERS / 2.0


def default_runner() -> Path:
    return Path.home() / "GitHub/TanksAndTemples/python_toolbox/evaluation/run.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the forked TanksAndTemples evaluator on a MaiCity mesh."
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        required=True,
        help="Independent MaiCity reference point cloud (normally sequence 02).",
    )
    parser.add_argument("--mesh", type=Path, required=True, help="Mesh to evaluate.")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for evaluator outputs and machine-readable metrics.",
    )
    parser.add_argument(
        "--evaluator-runner",
        type=Path,
        default=default_runner(),
        help="RuanJY fork's python_toolbox/evaluation/run.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate paths and print the fixed protocol without importing Open3D.",
    )
    return parser.parse_args()


def git_metadata(repository: Path) -> dict[str, str]:
    def git(*arguments: str) -> str:
        try:
            return subprocess.check_output(
                ["git", "-C", str(repository), *arguments],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {
        "repository": str(repository),
        "commit": git("rev-parse", "HEAD"),
        "remote": git("remote", "get-url", "origin"),
    }


def load_runner(path: Path) -> Any:
    # Quality runs are batch jobs; avoid importing the desktop Qt backend when
    # the evaluator creates its diagnostic precision/recall plots.
    os.environ.setdefault("MPLBACKEND", "Agg")
    sys.path.insert(0, str(path.parent))
    module_spec = importlib.util.spec_from_file_location("tnt_rjy_run", path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Cannot load evaluator module: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def read_metric_vector(path: Path) -> list[float]:
    values = [float(token) for token in path.read_text(encoding="utf-8").split()]
    if len(values) < 5:
        raise RuntimeError(f"Unexpected metric file contents: {path}")
    return values


def write_metrics(
    output: Path, runner: Path, ground_truth: Path, mesh: Path
) -> dict[str, Any]:
    metric_path = output / "__.prf_tau_plotstr.txt"
    precision, recall, f1, tau, plot_stretch = read_metric_vector(metric_path)[:5]
    repository = runner.parents[2]
    result: dict[str, Any] = {
        "status": "ok",
        "evaluator": "TanksAndTemples-RuanJY",
        "evaluator_runner": str(runner),
        "evaluator_repository": git_metadata(repository),
        "ground_truth": str(ground_truth),
        "mesh": str(mesh),
        "tau_m": tau,
        "voxel_size_m": VOXEL_SIZE_METERS,
        "sample_points": SAMPLE_POINTS,
        "plot_stretch": plot_stretch,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "outputs": sorted(
            {
                *(str(path.relative_to(output)) for path in output.iterdir() if path.is_file()),
                "metrics.csv",
                "metrics.json",
            }
        ),
    }
    (output / "metrics.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "status",
                "evaluator",
                "ground_truth",
                "mesh",
                "tau_m",
                "voxel_size_m",
                "sample_points",
                "precision",
                "recall",
                "f1",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "status": "ok",
            "evaluator": "TanksAndTemples-RuanJY",
            "ground_truth": str(ground_truth),
            "mesh": str(mesh),
            "tau_m": tau,
            "voxel_size_m": VOXEL_SIZE_METERS,
            "sample_points": SAMPLE_POINTS,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })
    return result


def main() -> int:
    args = parse_args()
    ground_truth = args.ground_truth.expanduser().resolve()
    mesh = args.mesh.expanduser().resolve()
    runner = args.evaluator_runner.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not ground_truth.is_file():
        raise FileNotFoundError(f"MaiCity reference point cloud not found: {ground_truth}")
    if not mesh.is_file():
        raise FileNotFoundError(f"Mesh not found: {mesh}")
    if not runner.is_file():
        raise FileNotFoundError(f"TanksAndTemples evaluator not found: {runner}")

    protocol = {
        "tau_m": TAU_METERS,
        "voxel_size_m": VOXEL_SIZE_METERS,
        "sample_points": SAMPLE_POINTS,
        "trajectory_alignment": False,
        "registration": False,
    }
    print(json.dumps({"protocol": protocol, "runner": str(runner)}, indent=2))
    if args.dry_run:
        return 0

    output.mkdir(parents=True, exist_ok=True)
    evaluator = load_runner(runner)
    evaluator.run_evaluation(str(ground_truth), str(mesh), str(output))
    result = write_metrics(output, runner, ground_truth, mesh)
    print(
        "precision: {precision:.6f} | recall: {recall:.6f} | "
        "f1: {f1:.6f}".format(**result)
    )
    print(f"Evaluation artifacts: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"evaluate_maicity_tnt.py: {error}", file=sys.stderr)
        raise
