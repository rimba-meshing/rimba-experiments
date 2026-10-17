"""The paper campaign and its short diagnostic mode."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from . import datasets, environment
from ..paper_results import inputs


def comparison_inputs(root: Path, raw: Path) -> None:
    directory = root / "comparisons"
    supplied = {"external_" + kind: str(directory / f"{kind}.csv") for kind in ("quality", "runtime") if (directory / f"{kind}.csv").is_file()}
    pdf = directory / "qualitative.pdf"
    if pdf.is_file():
        supplied["qualitative_pdf"] = {"file": str(pdf), "source": (directory / "qualitative-source.txt").read_text().strip()}
    if supplied:
        path = raw / "publication_inputs.json"
        path.write_text(json.dumps(supplied, indent=2) + "\n")
        parsed = inputs.load(path)
        for kind in ("quality", "runtime"):
            inputs.external_rows(parsed, kind)


def prepare_reference(dataset: Path, work: Path) -> dict:
    # Keep NumPy/OpenBLAS out of the orchestrator and benchmark processes.
    path = work / "raw/reference_preparation.json"
    code = ("from pathlib import Path; import json, sys; "
            "from tools.reproduction.reference import generate; "
            "record = generate(Path(sys.argv[1]), Path(sys.argv[2])); "
            "Path(sys.argv[3]).write_text(json.dumps(record, indent=2) + '\\n')")
    environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
    subprocess.run([sys.executable, "-c", code, str(dataset), str(work / "maicity_reference.ply"), str(path)], cwd=Path(__file__).parents[2], env=environment, check=True)
    return json.loads(path.read_text())


def protocol_command(root: Path, output: Path, staged: dict, runner: Path, frame_count: int | None = None) -> list[str]:
    counts = (frame_count, frame_count) if frame_count is not None else (1101, 100)
    command = [sys.executable, str(root / "tools/run_paper_protocol.py"),
            "--require-clean", "--paper-output", "--include-runtime-sequences", "--include-sensitivity",
            "--output", str(output / ".work/raw"), "--kitti-dataset", str(staged["kitti"]),
            "--maicity-dataset", str(staged["maicity"]), "--kitti-frame-count", str(counts[0]), "--maicity-frame-count", str(counts[1]),
            "--cmake", "cmake", "--build-jobs", "2", "--warmup-runs", "3", "--runs", "10", "--mesh-policy", "quality",
            "--quality-ground-truth", str(output / ".work/maicity_reference.ply"), "--quality-runner", str(runner)]
    if frame_count is not None:
        command += ["--runtime-frame-count", str(frame_count)]
    return command


def report_command(root: Path, output: Path, frame_count: int | None) -> list[str]:
    counts = (frame_count, frame_count) if frame_count is not None else (1101, 100)
    return [sys.executable, str(root / "tools/report_protocol.py"), str(output / ".work/raw"), "--output", str(output),
            "--expected-kitti-frames", str(counts[0]), "--expected-maicity-frames", str(counts[1])]


def destination(root: Path, output: Path | None, frame_count: int | None) -> Path:
    prefix = "diagnostic" if frame_count is not None else "full"
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = (output or root / "results/paper_protocol" / f"{prefix}_{stamp}").expanduser().resolve()
    if output.exists():
        raise ValueError(f"Output already exists; choose a new directory: {output}")
    if output.is_relative_to(root):
        ignored = subprocess.run(["git", "check-ignore", "--quiet", str(output)], cwd=root).returncode == 0
        if not ignored:
            raise ValueError("Inside this checkout, choose an output under results/; other outputs must be outside the checkout.")
    return output


def preview(root: Path, output: Path, selected: dict, runner: Path, frame_count: int | None) -> None:
    staged = {kind: output / ".work/datasets" / kind for kind in selected}
    print(f"Results: {output}")
    print("Prepare temporary dataset links and generate the reference from all 100 MaiCity 02 scans.")
    print(shlex.join(protocol_command(root, output, staged, runner, frame_count)))
    print(shlex.join(report_command(root, output, frame_count)))
    print("Dry run complete. No downloads, builds, experiments or result directories created.")


def run(root: Path, output: Path | None = None, frame_count: int | None = None, dry_run: bool = False) -> None:
    output = destination(root, output, frame_count)
    environment_record = environment.preflight(root)
    selected = datasets.sources(root, frame_count)
    runner = environment.evaluator(root, dry_run)
    if dry_run:
        preview(root, output, selected, runner, frame_count)
        return
    raw = output / ".work/raw"
    raw.mkdir(parents=True)
    (raw / "environment.json").write_text(json.dumps(environment_record, indent=2) + "\n")
    comparison_inputs(root, raw)
    staged = datasets.stage(selected, output / ".work")
    prepare_reference(staged["maicity"], output / ".work")
    subprocess.run(protocol_command(root, output, staged, runner, frame_count), cwd=root, check=True)
    subprocess.run(report_command(root, output, frame_count), cwd=root, check=True)
    print(f"Validated paper results: {output / 'report.pdf'}")
