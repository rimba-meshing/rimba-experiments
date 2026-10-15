#!/usr/bin/env python3
"""Build, measure, validate, and summarize the RIMBA protocol locally."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kitti-dataset", type=Path, default=env_path("RI_KITTI_DATASET"))
    parser.add_argument("--maicity-dataset", type=Path, default=env_path("RI_MAICITY_DATASET"))
    parser.add_argument("--quality-ground-truth", type=Path, default=env_path("RI_MAICITY_GROUND_TRUTH"))
    parser.add_argument("--quality-runner", type=Path, default=env_path("RI_TNT_RUNNER"))
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--build-jobs", type=int, default=2)
    parser.add_argument("--skip-quality", action="store_true", help="Omit geometric quality; label the report accordingly.")
    parser.add_argument("--diagnostic-frame-count", type=int, help="Use a short interval for both datasets, not the full protocol.")
    parser.add_argument("--output", type=Path, help="New result directory (timestamped by default).")
    parser.add_argument("--dry-run", action="store_true", help="Check prerequisites and print commands without writing results.")
    parser.add_argument("--report-only", type=Path, metavar="BUNDLE", help="Validate and summarize existing results without rebuilding or measuring.")
    args = parser.parse_args()
    if args.build_jobs < 1 or (args.diagnostic_frame_count is not None and args.diagnostic_frame_count < 1):
        parser.error("Build jobs and diagnostic frame count must be positive.")
    if args.report_only and args.output:
        parser.error("--report-only writes under BUNDLE/report; do not combine with --output.")
    for name in ("kitti_dataset", "maicity_dataset", "quality_ground_truth", "quality_runner", "report_only"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.expanduser().resolve())
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = "diagnostic" if args.diagnostic_frame_count else "full"
    args.output = (args.report_only or args.output or ROOT / "results/paper_protocol" / f"{prefix}_{stamp}").expanduser().resolve()
    if args.quality_ground_truth is None and args.maicity_dataset is not None:
        args.quality_ground_truth = args.maicity_dataset / "sequences/02/global.ply"
    return args


def capture(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError(f"Prerequisite command failed: {shlex.join(command)}\n{error.output}") from error


def check_python(quality: bool) -> dict[str, str]:
    packages = {"numpy": "numpy", "matplotlib": "matplotlib", "Pillow": "PIL"}
    if quality:
        packages["open3d-cpu"] = "open3d"
    # Import in a separate process so evaluation/reporting libraries do not
    # initialize worker pools or GPU contexts in the orchestration process.
    capture([sys.executable, "-c", "; ".join(f"import {module}" for module in packages.values())])
    return {name: importlib.metadata.version(name) for name in packages}


def check_dataset(root: Path | None, sequence: str, count: int, variable: str) -> None:
    if root is None:
        raise ValueError(f"Set {variable} or pass its dataset option; see README.md#datasets.")
    directory = root / "sequences" / sequence
    for name in ("poses.txt", "calib.txt"):
        if not (directory / name).is_file():
            raise ValueError(f"Missing input: {directory / name}")
    missing = [i for i in range(count) if not (directory / "velodyne" / f"{i:06d}.bin").is_file()]
    if missing:
        raise ValueError(f"Missing {sequence} frames in {directory}: first missing index {missing[0]}")


def check_quality(args: argparse.Namespace) -> None:
    if args.skip_quality:
        return
    if args.quality_ground_truth is None or not args.quality_ground_truth.is_file():
        raise ValueError("Supply RI_MAICITY_GROUND_TRUTH (independent sequence-02 global.ply), or --skip-quality.")
    runner = args.quality_runner
    if runner is None or not runner.is_file():
        raise ValueError("Supply RI_TNT_RUNNER; see README.md#quality-evaluation, or --skip-quality.")
    repo = runner.parents[2]
    if capture(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("The quality evaluator has tracked modifications.")


def preflight(args: argparse.Namespace, counts: tuple[int, int]) -> dict:
    if args.report_only:
        if not (args.output / "metadata.json").is_file():
            raise ValueError(f"No protocol manifest in {args.output}")
        return {"packages": check_python(False)}
    source = ROOT / "rimba"
    if not (source / "CMakeLists.txt").is_file():
        raise ValueError("Initialize the source with git submodule update --init --recursive.")
    compiler = os.environ.get("CXX", "c++")
    for executable in ("git", args.cmake, "nvcc", "nvidia-smi", "make", compiler):
        if shutil.which(executable) is None:
            raise ValueError(f"Required executable not found: {executable}")
    version = capture([args.cmake, "--version"])
    match = re.search(r"cmake version (\d+)\.(\d+)", version)
    if match is None or tuple(map(int, match.groups())) < (4, 2):
        raise ValueError("CMake 4.2 or newer is required.")
    if not Path("/usr/bin/time").is_file() or "GNU" not in capture(["/usr/bin/time", "--version"]):
        raise ValueError("GNU time at /usr/bin/time is required for CPU peak-memory measurements.")
    if not args.dry_run:
        for repo in (ROOT, source):
            if capture(["git", "-C", str(repo), "status", "--porcelain"]):
                raise ValueError(f"Commit or discard changes before reproduction: {repo}")
    check_dataset(args.kitti_dataset, "07", counts[0], "RI_KITTI_DATASET")
    check_dataset(args.maicity_dataset, "01", counts[1], "RI_MAICITY_DATASET")
    check_quality(args)
    return {
        "python": sys.version, "cmake": version, "nvcc": capture(["nvcc", "--version"]),
        "host_compiler": capture([compiler, "--version"]),
        "gpu": capture(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        "packages": check_python(not args.skip_quality),
    }


def protocol_command(args: argparse.Namespace, counts: tuple[int, int]) -> list[str]:
    command = [
        sys.executable, str(ROOT / "tools/run_paper_protocol.py"),
        "--require-clean", "--keep-ablation-meshes", "--output", str(args.output),
        "--kitti-dataset", str(args.kitti_dataset), "--maicity-dataset", str(args.maicity_dataset),
        "--kitti-frame-count", str(counts[0]), "--maicity-frame-count", str(counts[1]),
        "--cmake", args.cmake, "--build-jobs", str(args.build_jobs),
    ]
    if args.skip_quality:
        command.append("--skip-quality")
    else:
        command += ["--quality-ground-truth", str(args.quality_ground_truth), "--quality-runner", str(args.quality_runner)]
    return command


def result_commands(args: argparse.Namespace, counts: tuple[int, int]) -> list[list[str]]:
    check = [
        sys.executable, str(ROOT / "tools/check_protocol.py"), str(args.output),
        "--expected-kitti-frames", str(counts[0]), "--expected-maicity-frames", str(counts[1]),
        "--output", str(args.output / "report/verification.json"),
    ]
    if args.skip_quality:
        check.append("--skip-quality")
    report = [sys.executable, str(ROOT / "tools/report_protocol.py"), str(args.output)]
    return [check, report]


def main() -> None:
    args = parse_args()
    counts = (args.diagnostic_frame_count,) * 2 if args.diagnostic_frame_count else (1101, 100)
    if not args.report_only and args.output.exists():
        raise ValueError(f"Output already exists; select a new directory: {args.output}")
    if not args.report_only and args.output.is_relative_to(ROOT):
        ignored = subprocess.run(["git", "check-ignore", "--quiet", str(args.output)], cwd=ROOT).returncode == 0
        if not ignored:
            raise ValueError("Inside this checkout, choose an output under results/; other outputs must be outside the checkout.")
    environment = preflight(args, counts)
    commands = result_commands(args, counts)
    if not args.report_only:
        commands.insert(0, protocol_command(args, counts))
    for command in commands:
        print(shlex.join(command), flush=True)
    if args.dry_run:
        print("Prerequisites checked; no builds, measurements, or result files created.")
        return
    if not args.report_only:
        args.output.mkdir(parents=True)
        (args.output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
        (args.output / "reproduce-command.txt").write_text(shlex.join([sys.executable, str(ROOT / "reproduce.py"), *sys.argv[1:]]) + "\n")
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)
    print(f"Validated results and report: {args.output / 'report/README.md'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError, importlib.metadata.PackageNotFoundError) as error:
        print(f"reproduce.py: {error}", file=sys.stderr)
        raise SystemExit(1)
