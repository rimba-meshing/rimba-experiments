#!/usr/bin/env python3
"""Run the RIMBA experiments described in the repository README.

The script is intentionally orchestration-only: it does not change the
pipeline configuration and it never modifies tracked repository files. It
configures and builds three local CUDA variants, runs throughput and scheduler
measurements, collects memory in separate passes, and normalizes the output.

The default run is deliberately comprehensive and can take a long time on a
full KITTI 07 sequence.  Use ``--dry-run`` to inspect every command first and
the ``--skip-*`` switches to split the campaign into smaller, reviewable jobs.
All run logs and a machine-readable manifest are written below one output
directory.  Detailed memory uses the separate ``cuda-memory-native`` binary
and one sequential pass; coarse memory uses the normal benchmark binary for
each real scheduler variant and samples the GPU externally.
The script uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Callable, Iterable, Sequence

try:
    from benchmark_statistics import comparison_stats, parse_run_timings, summarize
except ModuleNotFoundError:  # Imported as ``tools.run_paper_protocol`` in tests.
    from tools.benchmark_statistics import comparison_stats, parse_run_timings, summarize


SCRIPT_VERSION = "2.0"
DEFAULT_MACRO_ERROR = 0.08
DEFAULT_CULL_RADIUS = 70.0
DEFAULT_HOLE_AREA = 50.0
DEFAULT_WARMUP_RUNS = 3
DEFAULT_MEASURED_RUNS = 10
FIXED_PIPELINE = {
    "vertex_mode": "filled-pixel-coarsened",
    "filled_pixel_fill": "iterative-5",
    "macro_cell_max_size": "16x16",
    "accumulated_fill_support": "enabled",
    "ri_thin_component_filter": "enabled",
    "stitcher": "current",
    "boundary_stitching": "enabled",
    "ri_frontier_stitching": "enabled",
    "local_seam_hole_filling": "enabled",
    "stitch_open_side_filter": "enabled",
    "proxy_mode": "polyline when blocker is enabled",
}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_cmake(repo: Path) -> str:
    candidate = repo / "build/cmake-venv/bin/cmake"
    return str(candidate) if candidate.is_file() else shutil.which("cmake") or "cmake"


def default_dataset(kind: str) -> Path:
    if kind == "kitti":
        return Path(os.environ.get(
            "RI_KITTI_DATASET",
            str(Path.home() / "Datasets/local/kitti_odom/kitti_data/dataset"),
        )).expanduser()
    return Path(os.environ.get(
        "RI_MAICITY_DATASET",
        str(Path.home() / "Datasets/local/mai_city/bin"),
    )).expanduser()


def default_quality_ground_truth() -> Path | None:
    value = os.environ.get("RI_MAICITY_GROUND_TRUTH")
    return Path(value).expanduser() if value else None


def default_quality_runner() -> Path | None:
    value = os.environ.get("RI_TNT_RUNNER")
    return Path(value).expanduser() if value else None


def parse_args() -> argparse.Namespace:
    repo = repository_root()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(
        description="Compile and run the RIMBA paper protocol."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=repo / "rimba",
        help="RIMBA source checkout (defaults to the pinned submodule).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo / "results/paper_protocol" / stamp,
        help="Artifact directory; a new timestamped directory is the default.",
    )
    parser.add_argument("--kitti-dataset", type=Path, default=default_dataset("kitti"))
    parser.add_argument("--maicity-dataset", type=Path, default=default_dataset("maicity"))
    parser.add_argument("--kitti-sequence", default="07")
    parser.add_argument("--maicity-sequence", default="01")
    parser.add_argument("--kitti-start-frame", type=int, default=0)
    parser.add_argument("--maicity-start-frame", type=int, default=0)
    parser.add_argument("--kitti-frame-count", type=int, default=None)
    parser.add_argument("--maicity-frame-count", type=int, default=None)
    parser.add_argument("--warmup-runs", type=int, default=DEFAULT_WARMUP_RUNS)
    parser.add_argument("--runs", type=int, default=DEFAULT_MEASURED_RUNS)
    parser.add_argument("--memory-warmup-runs", type=int, default=1)
    parser.add_argument("--memory-runs", type=int, default=1)
    parser.add_argument(
        "--sample-gpu-memory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Sample process VRAM through NVML during coarse memory runs.",
    )
    parser.add_argument(
        "--memory-sample-period",
        type=float,
        default=0.05,
        help="Period in seconds for the per-process NVML sampler (default: 0.05).",
    )
    parser.add_argument("--cmake", default=None)
    parser.add_argument("--build-jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--quality-ground-truth",
        type=Path,
        default=default_quality_ground_truth(),
        help=(
            "Independent MaiCity reference point cloud for the TanksAndTemples "
            "protocol; normally accumulated from sequence 02."
        ),
    )
    # Kept as a hidden compatibility alias.  Despite its old name, this value
    # was always passed as the reference point-cloud path, not as a directory.
    parser.add_argument(
        "--quality-dataset-dir",
        dest="quality_ground_truth",
        type=Path,
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--quality-python",
        default=sys.executable,
        help="Python interpreter used for the optional Tanks and Temples evaluator.",
    )
    parser.add_argument(
        "--quality-runner",
        type=Path,
        default=default_quality_runner(),
    )
    parser.add_argument("--configure", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--refresh-coarse-memory",
        action="store_true",
        help="Replace previously recorded coarse-memory rows while resuming.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse existing binaries instead of configuring/building presets.",
    )
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--keep-ablation-meshes", action="store_true")
    parser.add_argument("--mesh-policy", choices=("all", "quality", "none"), help="Override mesh retention for paper exports.")
    parser.add_argument("--max-triangle-dist", type=float, default=0.30, help="Shared continuity/edge limit in metres (paper reference: 0.30, sensitivity: 0.55).")
    parser.add_argument("--paper-output", action="store_true", help="Measure the paper's scopes without empty templates or auxiliary overlap passes.")
    parser.add_argument("--include-runtime-sequences", action="store_true", help="Also time KITTI 03/05/06/10 with the reference configuration.")
    parser.add_argument("--runtime-frame-count", type=int, help="Diagnostic frame count for the additional KITTI timing passes.")
    parser.add_argument("--skip-main", action="store_true")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--skip-memory", action="store_true")
    parser.add_argument("--skip-stage-timing", action="store_true")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.max_triangle_dist) or args.max_triangle_dist <= 0:
        parser.error("--max-triangle-dist must be finite and positive")
    if args.runtime_frame_count is not None and args.runtime_frame_count <= 0:
        parser.error("--runtime-frame-count must be positive")
    args.source_dir = args.source_dir.expanduser().resolve()
    args.cmake = args.cmake or default_cmake(args.source_dir)
    return args


def numeric_frame_indices(dataset: Path, sequence: str) -> list[int]:
    directory = dataset.expanduser() / "sequences" / sequence / "velodyne"
    if not directory.is_dir():
        raise FileNotFoundError(f"Frame directory not found: {directory}")
    indices = sorted(
        int(path.stem) for path in directory.glob("*.bin") if path.stem.isdigit()
    )
    if not indices:
        raise FileNotFoundError(f"No numeric .bin frames found in {directory}")
    expected = list(range(indices[0], indices[-1] + 1))
    if indices != expected:
        raise ValueError(f"Non-contiguous frame files in {directory}")
    return indices


def dataset_specs(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = []
    for kind, dataset, sequence, start, override in (
        ("kitti", args.kitti_dataset, args.kitti_sequence, args.kitti_start_frame, args.kitti_frame_count),
        ("maicity", args.maicity_dataset, args.maicity_sequence, args.maicity_start_frame, args.maicity_frame_count),
    ):
        indices = numeric_frame_indices(dataset, sequence)
        count = len(indices) if override is None else override
        if count <= 0 or start < indices[0] or start + count - 1 > indices[-1]:
            raise ValueError(
                f"Invalid frame range for {kind}: {start}..{start + count - 1}; "
                f"available range is {indices[0]}..{indices[-1]}"
            )
        specs.append({
            "kind": kind,
            "dataset": str(dataset.expanduser()),
            "sequence": sequence,
            "start": start,
            "count": count,
        })
    return specs


def git_metadata(repo: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "status": git("status", "--short"),
    }


def gpu_snapshot() -> list[str]:
    if shutil.which("nvidia-smi") is None:
        return []
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,"
         "pstate,clocks.current.sm,temperature.gpu,utilization.gpu",
         "--format=csv,noheader"],
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout.splitlines() if result.returncode == 0 else [result.stderr.strip()]


def write_command(path: Path, command: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(" ".join(shell_quote(item) for item in command) + "\n", encoding="utf-8")


def shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=+,-]+", value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def descendant_pids(root_pid: int) -> list[int]:
    """Find live descendants of a launcher such as ``/usr/bin/time``."""
    pending = [root_pid]
    descendants: list[int] = []
    while pending:
        parent = pending.pop()
        children_path = Path(f"/proc/{parent}/task/{parent}/children")
        try:
            children = [int(value) for value in children_path.read_text().split()]
        except (FileNotFoundError, OSError, ValueError):
            children = []
        for child in children:
            if child not in descendants:
                descendants.append(child)
                pending.append(child)
    return descendants


def execute(
    command: Sequence[str],
    log_path: Path,
    command_path: Path,
    dry_run: bool,
    env: dict[str, str] | None = None,
    process_started: Callable[[int], None] | None = None,
) -> None:
    write_command(command_path, command)
    print(f"$ {' '.join(shell_quote(item) for item in command)}")
    if dry_run:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                list(command), stdout=log, stderr=subprocess.STDOUT, env=env
            )
            if process_started is not None:
                process_started(process.pid)
            return_code = process.wait()
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
    if return_code != 0:
        raise RuntimeError(f"Command failed ({return_code}); see {log_path}")


def build_presets(args: argparse.Namespace, source_root: Path) -> dict[str, Path]:
    variants = {
        "benchmark": (
            source_root / "build/cuda-native-benchmark",
            {
                "CMAKE_BUILD_TYPE": "Release",
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION": "ON",
                "CMAKE_CUDA_ARCHITECTURES": "native",
                "RI_MESHING_ENABLE_OPENMP": "ON",
                "RI_MESHING_ENABLE_CUDA": "ON",
                "RI_MESHING_ENABLE_DETAILED_TIMING": "OFF",
                "RI_MESHING_ENABLE_DEBUG_EXPORT": "OFF",
                "RI_MESHING_BUILD_TESTS": "OFF",
            },
        ),
        "diagnostic": (
            source_root / "build/cuda-native-release",
            {
                "CMAKE_BUILD_TYPE": "Release",
                "CMAKE_CUDA_ARCHITECTURES": "native",
                "RI_MESHING_ENABLE_OPENMP": "ON",
                "RI_MESHING_ENABLE_CUDA": "ON",
                "RI_MESHING_BUILD_TESTS": "ON",
            },
        ),
        "memory": (
            source_root / "build/cuda-native-memory",
            {
                "CMAKE_BUILD_TYPE": "Release",
                "CMAKE_CUDA_ARCHITECTURES": "native",
                "RI_MESHING_ENABLE_OPENMP": "ON",
                "RI_MESHING_ENABLE_CUDA": "ON",
                "RI_MESHING_ENABLE_DETAILED_TIMING": "OFF",
                "RI_MESHING_ENABLE_DEBUG_EXPORT": "OFF",
                "RI_MESHING_ENABLE_MEMORY_INSTRUMENTATION": "ON",
                "RI_MESHING_BUILD_TESTS": "OFF",
            },
        ),
    }
    if not args.dry_run and not (source_root / "CMakeLists.txt").is_file():
        raise FileNotFoundError(f"RIMBA source checkout not found: {source_root}")
    for name, (build_dir, cache_variables) in variants.items():
        if args.skip_build:
            if not args.dry_run and not (build_dir / "ri_meshing").is_file():
                raise FileNotFoundError(f"Expected executable not found: {build_dir / 'ri_meshing'}")
            continue
        if args.configure:
            configure_command = [
                args.cmake,
                "-S", str(source_root),
                "-B", str(build_dir),
                "-G", "Unix Makefiles",
                *(f"-D{name}={value}" for name, value in cache_variables.items()),
            ]
            execute(
                configure_command,
                args.output / "build_logs" / f"{name}_configure.log",
                args.output / "commands" / f"{name}_configure.txt",
                args.dry_run,
            )
        execute(
            [args.cmake, "--build", str(build_dir), "--target", "ri_meshing",
             "-j", str(args.build_jobs)],
            args.output / "build_logs" / f"{name}_build.log",
            args.output / "commands" / f"{name}_build.txt",
            args.dry_run,
        )
        if not args.dry_run and not (build_dir / "ri_meshing").is_file():
            raise FileNotFoundError(f"Expected executable not found: {build_dir / 'ri_meshing'}")
    return {name: directory / "ri_meshing" for name, (directory, _) in variants.items()}


def common_app_args(spec: dict[str, Any]) -> list[str]:
    return [
        "--dataset", spec["dataset"],
        "--sequence", spec["sequence"],
        "--frame", str(spec["start"]),
        "--frame-count", str(spec["count"]),
        "--filled-pixel-macro-max-error", str(DEFAULT_MACRO_ERROR),
        "--accumulated-depth-cull-radius", str(DEFAULT_CULL_RADIUS),
        "--max-hole-ri-area-pixels", str(DEFAULT_HOLE_AREA),
    ]


def variant_args(variant: str) -> list[str]:
    if variant == "scheduler_none":
        return ["--frame-overlap", "none", "--disable-stitch-proxy-blocker"]
    if variant == "scheduler_pre_scan":
        return ["--frame-overlap", "pre-scan", "--disable-stitch-proxy-blocker"]
    if variant == "reference_pre_scan_polyline":
        return ["--frame-overlap", "pre-scan", "--stitch-proxy-blocker"]
    raise ValueError(f"Unknown scheduler variant: {variant}")


def variant_label(variant: str) -> str:
    return {
        "scheduler_none": "none",
        "scheduler_pre_scan": "pre-scan",
        "reference_pre_scan_polyline": "pre-scan + polyline proxy",
    }[variant]


_NVML_SUCCESS = 0
_NVML_ERROR_INSUFFICIENT_SIZE = 7
_NVML_VALUE_NOT_AVAILABLE = (1 << 64) - 1


class _NvmlMemoryInfo(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


class _NvmlProcessInfoV1(ctypes.Structure):
    _fields_ = [
        ("pid", ctypes.c_uint),
        ("used_gpu_memory", ctypes.c_ulonglong),
    ]


class _NvmlProcessInfoV2(ctypes.Structure):
    _fields_ = [
        ("pid", ctypes.c_uint),
        ("used_gpu_memory", ctypes.c_ulonglong),
        ("gpu_instance_id", ctypes.c_uint),
        ("compute_instance_id", ctypes.c_uint),
    ]


class _NvmlProcessInfoV3(ctypes.Structure):
    _fields_ = [
        ("pid", ctypes.c_uint),
        ("used_gpu_memory", ctypes.c_ulonglong),
        ("gpu_instance_id", ctypes.c_uint),
        ("compute_instance_id", ctypes.c_uint),
        ("used_gpu_cc_protected_memory", ctypes.c_ulonglong),
    ]


class NvmlProcessMemory:
    """Small ctypes-only NVML reader for memory belonging to one process."""

    def __init__(self) -> None:
        library_name = ctypes.util.find_library("nvidia-ml") or "libnvidia-ml.so.1"
        self.library = ctypes.CDLL(library_name)
        self._init = self._bind("nvmlInit_v2", [], ctypes.c_int)
        self._shutdown = self._bind("nvmlShutdown", [], ctypes.c_int)
        self._init_checked()
        self._count = self._bind(
            "nvmlDeviceGetCount_v2", [ctypes.POINTER(ctypes.c_uint)], ctypes.c_int
        )
        self._handle = self._bind(
            "nvmlDeviceGetHandleByIndex_v2",
            [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)],
            ctypes.c_int,
        )
        self._memory = self._bind(
            "nvmlDeviceGetMemoryInfo",
            [ctypes.c_void_p, ctypes.POINTER(_NvmlMemoryInfo)],
            ctypes.c_int,
        )
        self.devices = self._get_devices()
        self.process_functions = self._get_process_functions()
        if not self.devices or not self.process_functions:
            self.close()
            raise RuntimeError("NVML exposes no usable GPU/process memory query")

    def _bind(self, name: str, arguments: list[Any], result: Any) -> Any:
        function = getattr(self.library, name, None)
        if function is None:
            raise RuntimeError(f"NVML symbol not found: {name}")
        function.argtypes = arguments
        function.restype = result
        return function

    def _init_checked(self) -> None:
        if self._init() != _NVML_SUCCESS:
            raise RuntimeError("nvmlInit_v2 failed")

    def _get_devices(self) -> list[tuple[ctypes.c_void_p, str]]:
        count = ctypes.c_uint(0)
        if self._count(ctypes.byref(count)) != _NVML_SUCCESS:
            return []
        devices = []
        for index in range(count.value):
            handle = ctypes.c_void_p()
            if self._handle(index, ctypes.byref(handle)) != _NVML_SUCCESS:
                continue
            name = ctypes.create_string_buffer(96)
            get_name = self._bind(
                "nvmlDeviceGetName",
                [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint],
                ctypes.c_int,
            )
            label = f"gpu-{index}"
            if get_name(handle, name, ctypes.sizeof(name)) == _NVML_SUCCESS:
                label = name.value.decode("utf-8", errors="replace")
            devices.append((handle, label))
        return devices

    def _get_process_functions(self) -> list[tuple[Any, Any, str]]:
        functions = []
        structures = ((3, _NvmlProcessInfoV3), (2, _NvmlProcessInfoV2), (1, _NvmlProcessInfoV1))
        for kind in ("Compute", "Graphics"):
            for version, structure in structures:
                function = getattr(
                    self.library, f"nvmlDeviceGet{kind}RunningProcesses_v{version}", None
                )
                if function is None:
                    continue
                function.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_uint),
                    ctypes.POINTER(structure),
                ]
                function.restype = ctypes.c_int
                functions.append((function, structure, kind.lower()))
                break
        return functions

    def _process_memory_map(
        self, function: Any, structure: Any, handle: Any
    ) -> dict[int, int] | None:
        count = ctypes.c_uint(0)
        result = function(handle, ctypes.byref(count), None)
        if result not in (_NVML_SUCCESS, _NVML_ERROR_INSUFFICIENT_SIZE):
            return None
        if count.value == 0:
            return {}
        for _ in range(3):
            entries = (structure * count.value)()
            result = function(handle, ctypes.byref(count), entries)
            if result != _NVML_ERROR_INSUFFICIENT_SIZE:
                break
        if result != _NVML_SUCCESS:
            return None
        return {
            int(entry.pid): int(entry.used_gpu_memory)
            for entry in entries
            if int(entry.used_gpu_memory) != _NVML_VALUE_NOT_AVAILABLE
        }

    def sample(self, pids: Sequence[int]) -> list[dict[str, Any]]:
        samples = []
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        for handle, gpu_name in self.devices:
            memory_by_pid: dict[int, int] = {}
            query_succeeded = False
            for function, structure, _ in self.process_functions:
                process_map = self._process_memory_map(function, structure, handle)
                if process_map is None:
                    continue
                query_succeeded = True
                for pid, used_bytes in process_map.items():
                    memory_by_pid[pid] = max(memory_by_pid.get(pid, 0), used_bytes)
            active_pids = [pid for pid in pids if pid in memory_by_pid]
            if not query_succeeded or not active_pids:
                continue
            memory = _NvmlMemoryInfo()
            memory_result = self._memory(handle, ctypes.byref(memory))
            total = int(memory.total) if memory_result == _NVML_SUCCESS else 0
            used_bytes = sum(memory_by_pid[pid] for pid in active_pids)
            samples.append({
                "timestamp": timestamp,
                "pid": ",".join(str(pid) for pid in active_pids),
                "gpu": gpu_name,
                "memory_used_bytes": used_bytes,
                "memory_used_mib": used_bytes / (1024 * 1024),
                "memory_total_bytes": total,
                "memory_total_mib": total / (1024 * 1024),
                "sampler_backend": "nvml-process-tree",
            })
        return samples

    def close(self) -> None:
        if getattr(self, "_shutdown", None) is not None:
            self._shutdown()
            self._shutdown = None


class GpuSampler(threading.Thread):
    def __init__(self, period: float) -> None:
        super().__init__(daemon=True)
        self.period = period
        self.stop_event = threading.Event()
        self.samples: list[dict[str, Any]] = []
        self.pid: int | None = None
        self.process_pids: set[int] = set()
        self.backend = "nvml-process-tree"
        self.error: str | None = None
        self.api: NvmlProcessMemory | None = None

    def start_for_pid(self, pid: int) -> None:
        self.pid = pid
        try:
            self.api = NvmlProcessMemory()
        except (OSError, RuntimeError) as error:
            self.backend = "unavailable"
            self.error = str(error)
            print(f"WARNING: process VRAM sampler unavailable: {error}", file=sys.stderr)
            return
        self.start()

    def run(self) -> None:
        while not self.stop_event.is_set():
            if self.api is not None and self.pid is not None:
                pids = [self.pid, *descendant_pids(self.pid)]
                rows = self.api.sample(pids)
                for row in rows:
                    self.process_pids.update(int(value) for value in row["pid"].split(","))
                    row["launcher_pid"] = self.pid
                self.samples.extend(rows)
            self.stop_event.wait(self.period)

    def stop(self) -> None:
        self.stop_event.set()
        if self.is_alive():
            self.join(timeout=max(1.0, self.period * 2.0))
        if self.api is not None:
            self.api.close()
            self.api = None


def clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("RI_STITCH_DEBUG", None)
    env.pop("CUDA_LAUNCH_BLOCKING", None)
    return env


def parse_summary(log_text: str) -> dict[str, Any]:
    patterns = {
        "frame_count": r"^Frames:\s+(\d+) starting at (\d+)",
        "vertices": r"^Vertices:\s+([\d,]+)",
        "faces": r"^Faces:\s+([\d,]+)",
        "warmup_runs": r"^Warmup runs:\s+(\d+)",
        "measured_runs": r"^Measured runs:\s+(\d+)",
        "warmup_frame_count": r"^Warmup frame count:\s+(\d+)",
        "total_ms": r"^Multi-frame call time without dataset I/O or PLY write:\s+([\d.eE+-]+) ms",
        "ms_per_frame": r"^Multi-frame call time per frame:\s+([\d.eE+-]+) ms",
    }

    def number(text: str) -> float:
        return float(text.replace(",", ""))

    def integer(text: str) -> int:
        return int(text.replace(",", ""))

    parsed: dict[str, Any] = {
        "frames": [],
        "stages": [],
        "timeline": [],
        "memory": [],
        "run_timings": [],
    }
    frame_re = re.compile(
        r"^Frame\s+(\d+):\s+([\d.eE+-]+) ms \| points (\d+) \| new vertices (\d+) \| "
        r"new faces (\d+) \| stitch faces (\d+) \| hole faces (\d+) \| total vertices (\d+) \| "
        r"total faces (\d+)"
    )
    stage_re = re.compile(r"^\s{2}(\S+):\s+([\d.eE+-]+) ms$")
    timeline_re = re.compile(r"^overlap\.timeline\s+t_ms=([\d.eE+-]+)\s+frame=(-?\d+)\s+event=(\S+)(?:\s+(.*))?$")
    memory_re = re.compile(r"^memory\.stage\s+frame=(-?\d+)\s+stage=(\S+)\s+(.*)$")

    def memory_value(value: str) -> int | float | str:
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?[\d.eE+]+", value):
            return float(value)
        return value

    current_frame: int | None = None
    for line in log_text.splitlines():
        for key, pattern in patterns.items():
            match = re.match(pattern, line)
            if match:
                parsed[key] = number(match.group(1)) if key in {"total_ms", "ms_per_frame"} else integer(match.group(1))
                if key == "frame_count":
                    parsed["start_frame"] = integer(match.group(2))
                break
        frame_match = frame_re.match(line)
        if frame_match:
            current_frame = integer(frame_match.group(1))
            parsed["frames"].append({
                "frame": current_frame,
                "frame_ms": number(frame_match.group(2)),
                "points": integer(frame_match.group(3)),
                "new_vertices": integer(frame_match.group(4)),
                "new_faces": integer(frame_match.group(5)),
                "stitch_faces": integer(frame_match.group(6)),
                "hole_faces": integer(frame_match.group(7)),
                "total_vertices": integer(frame_match.group(8)),
                "total_faces": integer(frame_match.group(9)),
            })
            continue
        stage_match = stage_re.match(line)
        if stage_match and current_frame is not None:
            parsed["stages"].append({
                "frame": current_frame,
                "stage": stage_match.group(1),
                "milliseconds": number(stage_match.group(2)),
            })
        timeline_match = timeline_re.match(line)
        if timeline_match:
            parsed["timeline"].append({
                "time_ms": number(timeline_match.group(1)),
                "frame": integer(timeline_match.group(2)),
                "event": timeline_match.group(3),
                "details": timeline_match.group(4) or "",
            })
        memory_match = memory_re.match(line)
        if memory_match:
            fields: dict[str, Any] = {}
            for token in memory_match.group(3).split():
                key, separator, value = token.partition("=")
                if separator:
                    fields[key] = memory_value(value)
            snapshot = {
                "frame": integer(memory_match.group(1)),
                "stage": memory_match.group(2),
                **fields,
            }
            snapshot.setdefault("pass_kind", "unknown")
            snapshot.setdefault("run_index", -1)
            parsed["memory"].append(snapshot)
    parsed["run_timings"] = [
        {"run_index": index, "call_time_ms": value}
        for index, value in enumerate(parse_run_timings(log_text))
    ]
    required = {"vertices", "faces", "measured_runs", "total_ms", "ms_per_frame"}
    missing = sorted(required - parsed.keys())
    if missing:
        raise ValueError(f"Missing summary fields {missing}")
    return parsed


def parse_cpu_max_rss(time_path: Path) -> int | None:
    if not time_path.is_file():
        return None
    match = re.search(
        r"Maximum resident set size \(kbytes\):\s+(\d+)",
        time_path.read_text(encoding="utf-8", errors="replace"),
    )
    return int(match.group(1)) * 1024 if match else None


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def run_application(
    args: argparse.Namespace,
    spec: dict[str, Any],
    variant: str,
    run_kind: str,
    binary: Path,
    run_root: Path,
    keep_mesh: bool,
    timing: str = "summary",
    overlap_timeline: bool = False,
    memory_mode: str = "none",
    warmup_runs: int | None = None,
    measured_runs: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if memory_mode not in {"none", "detailed", "coarse"}:
        raise ValueError(f"Unknown memory mode: {memory_mode}")
    is_memory = memory_mode != "none"
    detailed_memory = memory_mode == "detailed"
    coarse_memory = memory_mode == "coarse"
    run_id = f"{spec['kind']}_{variant}_{run_kind}"
    log_path = run_root / "logs" / f"{run_id}.log"
    command_path = run_root / "commands" / f"{run_id}.txt"
    time_path = run_root / "memory" / f"{run_id}.time.txt"
    mesh_path = run_root / "meshes" / f"{run_id}.ply" if keep_mesh else Path("/dev/null")
    if is_memory:
        (run_root / "memory").mkdir(parents=True, exist_ok=True)
    effective_warmup = warmup_runs if warmup_runs is not None else (args.memory_warmup_runs if is_memory else args.warmup_runs)
    effective_runs = measured_runs if measured_runs is not None else (args.memory_runs if is_memory else args.runs)
    command = [str(binary), *common_app_args(spec), *variant_args(variant),
               "--max-triangle-dist", str(args.max_triangle_dist),
               "--warmup-runs", str(effective_warmup),
               "--runs", str(effective_runs),
               "--timing", timing, "--output", str(mesh_path)]
    if overlap_timeline:
        command.extend(["--overlap-timeline", "--overlap-timeline-sync"])
    if is_memory and Path("/usr/bin/time").is_file():
        command = ["/usr/bin/time", "-v", "-o", str(time_path), *command]
    sampler = GpuSampler(args.memory_sample_period) if coarse_memory and args.sample_gpu_memory and not args.dry_run else None
    try:
        execute(
            command,
            log_path,
            command_path,
            args.dry_run,
            clean_environment(),
            sampler.start_for_pid if sampler else None,
        )
    finally:
        if sampler:
            sampler.stop()
    if args.dry_run:
        return ({"run_id": run_id, "status": "planned"}, {}, [], [], [], [])
    text = log_path.read_text(encoding="utf-8", errors="replace")
    summary = parse_summary(text)
    row = {
        "run_id": run_id,
        "dataset": spec["kind"],
        "sequence": spec["sequence"],
        "start_frame": spec["start"],
        "frame_count": spec["count"],
        "frame_end": spec["start"] + spec["count"] - 1,
        "variant": variant,
        "variant_label": variant_label(variant),
        "run_kind": run_kind,
        "effective_scheduling": "sequential (detailed memory build)" if detailed_memory else variant_label(variant),
        "memory_mode": memory_mode,
        "build": (
            "cuda-native-memory" if detailed_memory
            else "cuda-native-release" if timing != "summary"
            else "cuda-benchmark-native"
        ),
        "timing_mode": timing,
        "warmup_runs": summary.get("warmup_runs"),
        "measured_runs": summary.get("measured_runs"),
        "total_ms": summary.get("total_ms"),
        "ms_per_frame": summary.get("ms_per_frame"),
        "run_sample_count": None,
        "run_time_mean_ms": None,
        "run_time_std_ms": None,
        "run_time_std_ms_per_frame": None,
        "run_time_ci95_low_ms_per_frame": None,
        "run_time_ci95_high_ms_per_frame": None,
        "run_time_ci95_half_width_ms_per_frame": None,
        "vertices": summary.get("vertices"),
        "faces": summary.get("faces"),
        "output_bytes": mesh_path.stat().st_size if keep_mesh and mesh_path.is_file() else None,
        "cpu_max_rss_bytes": parse_cpu_max_rss(time_path) if is_memory else None,
        "gpu_sampler_backend": sampler.backend if sampler else None,
        "gpu_sampler_error": sampler.error if sampler else None,
        "gpu_pid": ",".join(str(pid) for pid in sorted(sampler.process_pids)) if sampler else None,
        "gpu_launcher_pid": sampler.pid if sampler else None,
        "log": str(log_path),
        **FIXED_PIPELINE,
    }
    run_samples = [item["call_time_ms"] for item in summary["run_timings"]]
    if run_samples:
        run_statistics = summarize(run_samples, spec["count"])
        row.update({
            "run_sample_count": run_statistics["sample_count"],
            "run_time_mean_ms": run_statistics["mean_ms"],
            "run_time_std_ms": run_statistics["std_ms"],
            "run_time_std_ms_per_frame": run_statistics["std_ms_per_frame"],
            "run_time_ci95_low_ms_per_frame": run_statistics["ci95_low_ms_per_frame"],
            "run_time_ci95_high_ms_per_frame": run_statistics["ci95_high_ms_per_frame"],
            "run_time_ci95_half_width_ms_per_frame": run_statistics[
                "ci95_half_width_ms_per_frame"
            ],
        })
    frame_rows = [dict(row, **frame) for frame in summary["frames"]]
    stage_rows = [dict(row, **stage) for stage in summary["stages"]]
    timeline_rows = [dict(row, **event) for event in summary["timeline"]]
    memory_rows = [dict(row, **snapshot) for snapshot in summary["memory"]]
    if sampler:
        write_csv(run_root / "memory" / f"{run_id}.gpu.csv", sampler.samples)
        memory_values = [item["memory_used_mib"] for item in sampler.samples]
        row["gpu_baseline_memory_mib"] = min(memory_values, default=None)
        row["gpu_max_memory_mib"] = max(memory_values, default=None)
        if memory_values:
            row["gpu_peak_delta_mib"] = max(memory_values) - min(memory_values)
    return row, summary, frame_rows, stage_rows, timeline_rows, memory_rows


def run_timing_rows_for(row: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach run-level raw samples to the same experiment identity."""

    identity = {
        key: row.get(key)
        for key in (
            "run_id", "dataset", "sequence", "start_frame", "frame_count",
            "frame_end", "variant", "variant_label", "run_kind", "build",
            "timing_mode", "memory_mode",
        )
    }
    return [
        {
            **identity,
            "run_index": item["run_index"],
            "call_time_ms": item["call_time_ms"],
            "time_per_frame_ms": item["call_time_ms"] / int(row["frame_count"]),
        }
        for item in summary.get("run_timings", [])
    ]


def write_throughput_statistics(
    rows: list[dict[str, Any]],
    run_timing_rows: list[dict[str, Any]],
    root: Path,
) -> None:
    """Write run-level statistics and scheduler reduction intervals."""

    throughput_rows = [
        row for row in rows
        if row.get("run_kind") == "throughput" and row.get("status") == "ok"
    ]
    statistics_rows: list[dict[str, Any]] = []
    samples_by_run: dict[str, list[float]] = {}
    for raw in run_timing_rows:
        run_id = str(raw.get("run_id", ""))
        try:
            samples_by_run.setdefault(run_id, []).append(float(raw["call_time_ms"]))
        except (KeyError, TypeError, ValueError):
            continue
    for row in throughput_rows:
        samples = samples_by_run.get(str(row["run_id"]), [])
        if not samples:
            continue
        summary = summarize(samples, int(row["frame_count"]))
        statistics_rows.append({
            "run_id": row["run_id"],
            "dataset": row["dataset"],
            "sequence": row["sequence"],
            "frame_count": row["frame_count"],
            "variant": row["variant"],
            "variant_label": row["variant_label"],
            "sample_count": summary["sample_count"],
            "mean_ms": summary["mean_ms"],
            "std_ms": summary["std_ms"],
            "mean_ms_per_frame": summary["mean_ms_per_frame"],
            "std_ms_per_frame": summary["std_ms_per_frame"],
            "ci95_half_width_ms_per_frame": summary["ci95_half_width_ms_per_frame"],
            "ci95_low_ms_per_frame": summary["ci95_low_ms_per_frame"],
            "ci95_high_ms_per_frame": summary["ci95_high_ms_per_frame"],
            "ci95_critical_t": summary["ci95_critical_t"],
        })
    write_csv(root / "throughput_stats.csv", statistics_rows)

    by_dataset = {
        (row["dataset"], row["sequence"]): row
        for row in throughput_rows
        if row.get("variant") == "scheduler_none"
    }
    comparison_rows: list[dict[str, Any]] = []
    for row in throughput_rows:
        if row.get("variant") == "scheduler_none":
            continue
        key = (row["dataset"], row["sequence"])
        baseline = by_dataset.get(key)
        baseline_samples = samples_by_run.get(str(baseline["run_id"]), []) if baseline else []
        variant_samples = samples_by_run.get(str(row["run_id"]), [])
        if not baseline_samples or not variant_samples:
            continue
        comparison = comparison_stats(
            baseline_samples, variant_samples, int(row["frame_count"])
        )
        comparison_rows.append({
            "dataset": row["dataset"],
            "sequence": row["sequence"],
            "baseline_variant": baseline["variant"],
            "variant": row["variant"],
            **comparison,
        })
    write_csv(root / "throughput_comparisons.csv", comparison_rows)


def stage_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[float]] = {}
    for row in rows:
        key = (row["dataset"], row["variant"], row["stage"])
        grouped.setdefault(key, []).append(float(row["milliseconds"]))
    output = []
    for (dataset, variant, stage), values in sorted(grouped.items()):
        output.append({
            "dataset": dataset,
            "variant": variant,
            "stage": stage,
            "sample_frames": len(values),
            "mean_ms": sum(values) / len(values),
            "max_ms": max(values),
            "sum_ms": sum(values),
        })
    return output


def write_qualitative_manifest(args: argparse.Namespace, specs: list[dict[str, Any]], rows: list[dict[str, Any]], root: Path) -> None:
    qualitative = root / "qualitative"
    qualitative.mkdir(parents=True, exist_ok=True)
    entries = []
    for spec in specs:
        baseline = next((row for row in rows if row.get("dataset") == spec["kind"] and row.get("run_kind") == "throughput" and row.get("variant") == "reference_pre_scan_polyline"), None)
        frames = [spec["start"], spec["start"] + spec["count"] // 2, spec["start"] + spec["count"] - 1]
        entries.append({
            "dataset": spec["kind"],
            "sequence": spec["sequence"],
            "suggested_frames": ",".join(map(str, sorted(set(frames)))),
            "baseline_mesh": baseline.get("output_mesh") if baseline else "",
            "note": "Use the interactive viewer with the retained baseline PLY; camera selection is intentionally manual.",
        })
    write_csv(qualitative / "qualitative_manifest.csv", entries)
    (qualitative / "README.md").write_text(
        "# Qualitative figure inputs\n\n"
        "The protocol deliberately does not choose a camera automatically. "
        "Use the baseline PLY from `meshes/` when `--keep-ablation-meshes` is "
        "enabled, or the retained reference output from the throughput run. "
        "The CSV lists suggested early/middle/late frames for manual review.\n",
        encoding="utf-8",
    )


def write_artifact_readme(specs: list[dict[str, Any]], root: Path) -> None:
    lines = [
        "# Paper protocol run",
        "",
        "Produced by `tools/run_paper_protocol.py`.",
        "The executable's end-to-end time excludes dataset input and final PLY write.",
        "Clean throughput, coarse-memory, and detailed-memory passes are kept separate.",
        "",
        "## Dataset windows",
        "",
    ]
    lines.extend(
        f"- {spec['kind']}: sequence `{spec['sequence']}`, frames "
        f"`{spec['start']}..{spec['start'] + spec['count'] - 1}`"
        for spec in specs
    )
    lines.extend([
        "",
        "## Output files",
        "",
        "- `results.csv`: every throughput, memory, and stage run.",
        "- `frame_metrics.csv`: per-frame time and mesh-size counters.",
        "- `run_timings.csv`: one raw total-call timing per measured run; the run-level samples are the statistical observations.",
        "- `throughput_stats.csv`: mean, sample std, and Student-t 95% CI per throughput variant.",
        "- `throughput_comparisons.csv`: scheduler reductions against the sequential baseline, with a Welch-derived 95% CI.",
        "- `stage_timings.csv` and `stage_summary.csv`: diagnostic per-stage measurements.",
        "- `scheduler_timeline.csv`: overlap timeline events, when enabled.",
        "- `memory_stages.csv`: per-frame/per-stage tracked host/device memory from one sequential detailed-memory pass; snapshots include `pass_kind` and `run_index`.",
        "- `memory/`: CPU `/usr/bin/time -v` reports and coarse per-process-tree NVML samples for the three real scheduler variants.",
        "- `quality.csv`: TanksAndTemples P/R/F1 rows per retained MaiCity mesh, or an explicit not-configured status.",
        "- `qualitative/`: suggested frames and retained PLY paths for manual figures.",
        "- `external_comparison.csv`: template for externally reproduced methods.",
        "",
        "Exact commands, commit, GPU snapshot, arguments, and repository status are in "
        "`commands/` and `metadata.json`.",
    ])
    (root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_optional_quality(
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    artifact_root: Path,
    repository_root: Path,
) -> list[dict[str, Any]]:
    if args.skip_quality:
        return [{"status": "skipped", "reason": "--skip-quality"}]
    if args.quality_ground_truth is None:
        return [{
            "status": "not_configured",
            "reason": "Provide --quality-ground-truth or RI_MAICITY_GROUND_TRUTH.",
        }]
    ground_truth = args.quality_ground_truth.expanduser().resolve()
    if not ground_truth.is_file():
        return [{"status": "not_configured", "reason": f"Reference not found: {ground_truth}"}]
    if args.quality_runner is None:
        return [{"status": "not_configured", "reason": "Provide --quality-runner or RI_TNT_RUNNER."}]
    evaluator_runner = args.quality_runner.expanduser().resolve()
    if not evaluator_runner.is_file():
        return [{"status": "not_configured", "reason": f"Evaluator not found: {evaluator_runner}"}]
    quality_script = repository_root / "tools/evaluate_maicity_tnt.py"
    if not quality_script.is_file():
        return [{"status": "not_configured", "reason": f"Quality wrapper not found: {quality_script}"}]
    candidates = [
        row for row in rows
        if row.get("dataset") == "maicity"
        and row.get("run_kind") == "throughput"
        and row.get("output_mesh")
    ]
    if not candidates:
        return [{"status": "not_run", "reason": "No retained MaiCity PLY is available."}]

    results: list[dict[str, Any]] = []
    for candidate in candidates:
        variant = str(candidate["variant"])
        output = artifact_root / "quality" / "maicity_tanks_and_temples" / variant
        log = artifact_root / "quality" / f"maicity_tanks_and_temples_{variant}.log"
        command = [
            args.quality_python,
            str(quality_script),
            "--ground-truth",
            str(ground_truth),
            "--mesh",
            str(candidate["output_mesh"]),
            "--output",
            str(output),
            "--evaluator-runner",
            str(evaluator_runner),
        ]
        execute(
            command,
            log,
            artifact_root / "commands" / f"quality_maicity_{variant}.txt",
            args.dry_run,
        )
        if args.dry_run:
            results.append({
                "status": "planned",
                "dataset": "maicity",
                "variant": variant,
                "ground_truth": str(ground_truth),
                "log": str(log),
            })
            continue
        metrics_path = output / "metrics.json"
        if not metrics_path.is_file():
            raise RuntimeError(f"Quality wrapper did not write {metrics_path}")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        results.append({
            "status": "ok",
            "dataset": "maicity",
            "variant": variant,
            "ground_truth": str(ground_truth),
            "evaluator": metrics.get("evaluator"),
            "evaluator_commit": metrics.get("evaluator_repository", {}).get("commit"),
            "tau_m": metrics.get("tau_m"),
            "voxel_size_m": metrics.get("voxel_size_m"),
            "sample_points": metrics.get("sample_points"),
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("f1"),
            "log": str(log),
        })
    return results


def write_external_template(root: Path) -> None:
    write_csv(root / "external_comparison.csv", [{
        "method": "",
        "version_or_commit": "",
        "hardware": "",
        "dataset": "",
        "sequence": "",
        "poses": "",
        "runtime_total_ms": "",
        "runtime_ms_per_frame": "",
        "cpu_memory_bytes": "",
        "gpu_memory_bytes": "",
        "vertices": "",
        "faces": "",
        "precision": "",
        "recall": "",
        "f1": "",
        "source": "",
        "notes": "Fill only after reproducing the external method under a comparable protocol.",
    }])


def main() -> int:
    args = parse_args()
    root = repository_root()
    source_root = args.source_dir
    args.output = args.output.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "script_version": SCRIPT_VERSION,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": str(root),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": sys.version,
        "gpu_before": gpu_snapshot(),
        "git": git_metadata(root),
        "source_git": git_metadata(source_root),
        "arguments": vars(args),
    }
    metadata["arguments"] = {key: str(value) if isinstance(value, Path) else value for key, value in metadata["arguments"].items()}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if args.require_clean and (metadata["git"]["status"] or metadata["source_git"]["status"]):
        raise RuntimeError("Experiment or source checkout is dirty; omit --require-clean only when intentional.")
    if metadata["git"]["status"] or metadata["source_git"]["status"]:
        print("WARNING: experiment or source checkout has uncommitted changes; status recorded in metadata.json", file=sys.stderr)

    specs = dataset_specs(args)
    for spec in specs:
        print(f"{spec['kind']}: sequence {spec['sequence']}, frames {spec['start']}..{spec['start'] + spec['count'] - 1}")
    if args.warmup_runs < 0 or args.runs <= 0 or args.memory_warmup_runs < 0 or args.memory_runs <= 0:
        raise ValueError("Warm-up runs must be >= 0 and measured runs must be > 0")
    binaries = build_presets(args, source_root)
    rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    memory_rows: list[dict[str, Any]] = []
    run_timing_rows: list[dict[str, Any]] = []
    completed = set()
    result_file = args.output / "results.csv"
    if args.resume and result_file.is_file():
        rows.extend(csv_rows(result_file))
        frame_rows.extend(csv_rows(args.output / "frame_metrics.csv"))
        stage_rows.extend(csv_rows(args.output / "stage_timings.csv"))
        timeline_rows.extend(csv_rows(args.output / "scheduler_timeline.csv"))
        memory_rows.extend(csv_rows(args.output / "memory_stages.csv"))
        run_timing_rows.extend(csv_rows(args.output / "run_timings.csv"))
        completed = {row["run_id"] for row in rows if row.get("status") == "ok"}

    if args.refresh_coarse_memory:
        refreshed_ids = {
            row["run_id"] for row in rows if row.get("run_kind") == "memory_coarse"
        }
        if refreshed_ids:
            rows = [row for row in rows if row.get("run_id") not in refreshed_ids]
            frame_rows = [row for row in frame_rows if row.get("run_id") not in refreshed_ids]
            stage_rows = [row for row in stage_rows if row.get("run_id") not in refreshed_ids]
            timeline_rows = [row for row in timeline_rows if row.get("run_id") not in refreshed_ids]
            memory_rows = [row for row in memory_rows if row.get("run_id") not in refreshed_ids]
            run_timing_rows = [row for row in run_timing_rows if row.get("run_id") not in refreshed_ids]
            completed.difference_update(refreshed_ids)

    def persist() -> None:
        write_csv(result_file, rows)
        write_csv(args.output / "frame_metrics.csv", frame_rows)
        write_csv(args.output / "stage_timings.csv", stage_rows)
        if not args.paper_output:
            write_csv(args.output / "stage_summary.csv", stage_summary(stage_rows))
        if not args.paper_output or timeline_rows:
            write_csv(args.output / "scheduler_timeline.csv", timeline_rows)
        write_csv(args.output / "memory_stages.csv", memory_rows)
        write_csv(args.output / "run_timings.csv", run_timing_rows)
        write_throughput_statistics(rows, run_timing_rows, args.output)

    variants = ["scheduler_none", "scheduler_pre_scan", "reference_pre_scan_polyline"]
    for spec in specs:
        selected = ["reference_pre_scan_polyline"] if args.skip_ablation else variants
        if args.skip_main:
            selected = [] if args.skip_ablation else [item for item in selected if item != "reference_pre_scan_polyline"]
        for variant in selected:
            run_id = f"{spec['kind']}_{variant}_throughput"
            if run_id in completed:
                print(f"Skipping completed run {run_id}")
                continue
            keep_mesh = variant == "reference_pre_scan_polyline" or args.keep_ablation_meshes
            if args.mesh_policy:
                keep_mesh = args.mesh_policy == "all" or (args.mesh_policy == "quality" and spec["kind"] == "maicity")
            row, summary, frames, stages, timeline, memory_snapshots = run_application(
                args, spec, variant, "throughput", binaries["benchmark"], args.output,
                keep_mesh=keep_mesh,
            )
            if keep_mesh and row.get("output_bytes") is not None:
                row["output_mesh"] = str(args.output / "meshes" / f"{run_id}.ply")
            row["status"] = "planned" if args.dry_run else "ok"
            rows.append(row)
            frame_rows.extend(frames)
            stage_rows.extend(stages)
            timeline_rows.extend(timeline)
            memory_rows.extend(memory_snapshots)
            run_timing_rows.extend(run_timing_rows_for(row, summary))
            persist()
        if not args.skip_memory and selected:
            detailed_run_id = f"{spec['kind']}_scheduler_none_memory_detailed"
            if detailed_run_id not in completed:
                row, summary, frames, stages, timeline, memory_snapshots = run_application(
                    args, spec, "scheduler_none", "memory_detailed", binaries["memory"], args.output,
                    keep_mesh=False, memory_mode="detailed",
                )
                row["status"] = "planned" if args.dry_run else "ok"
                rows.append(row)
                frame_rows.extend(frames)
                stage_rows.extend(stages)
                timeline_rows.extend(timeline)
                memory_rows.extend(memory_snapshots)
                run_timing_rows.extend(run_timing_rows_for(row, summary))
                persist()
            for variant in selected:
                run_id = f"{spec['kind']}_{variant}_memory_coarse"
                if run_id in completed:
                    continue
                row, summary, frames, stages, timeline, memory_snapshots = run_application(
                    args, spec, variant, "memory_coarse", binaries["benchmark"], args.output,
                    keep_mesh=False, memory_mode="coarse",
                )
                row["status"] = "planned" if args.dry_run else "ok"
                rows.append(row)
                frame_rows.extend(frames)
                stage_rows.extend(stages)
                timeline_rows.extend(timeline)
                memory_rows.extend(memory_snapshots)
                run_timing_rows.extend(run_timing_rows_for(row, summary))
                persist()
    if not args.skip_stage_timing:
        for spec in specs:
            for timing, overlap, label in (("instrumented", True, "stage_overlap"), ("detailed", False, "stage_sequential")):
                if args.paper_output and overlap:
                    continue
                variant = "reference_pre_scan_polyline" if overlap else "scheduler_none"
                run_id = f"{spec['kind']}_{variant}_{label}"
                if run_id in completed:
                    continue
                row, summary, frames, stages, timeline, memory_snapshots = run_application(
                    args, spec, variant, label, binaries["diagnostic"], args.output,
                    keep_mesh=False, timing=timing, overlap_timeline=overlap,
                    warmup_runs=0, measured_runs=1,
                )
                row["status"] = "planned" if args.dry_run else "ok"
                rows.append(row)
                frame_rows.extend(frames)
                stage_rows.extend(stages)
                timeline_rows.extend(timeline)
                memory_rows.extend(memory_snapshots)
                run_timing_rows.extend(run_timing_rows_for(row, summary))
                persist()
    if args.include_runtime_sequences:
        from paper_results.runtime import measure
        measure(args, binaries["benchmark"])
    if not args.paper_output:
        write_qualitative_manifest(args, specs, rows, args.output)
        write_external_template(args.output)
        write_artifact_readme(specs, args.output)
    if not args.paper_output or not args.skip_quality:
        write_csv(args.output / "quality.csv", run_optional_quality(args, rows, args.output, root))
    metadata["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    metadata["result_files"] = [str(path.relative_to(args.output)) for path in sorted(args.output.rglob("*")) if path.is_file()]
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    persist()
    print(f"Paper protocol artifacts: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"run_paper_protocol.py: {error}", file=sys.stderr)
        raise
