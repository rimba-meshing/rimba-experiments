"""The single fixed campaign used by reproduce.py."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
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


def protocol_command(root: Path, output: Path, staged: dict, runner: Path) -> list[str]:
    return [sys.executable, str(root / "tools/run_paper_protocol.py"),
            "--require-clean", "--paper-output", "--include-runtime-sequences", "--include-sensitivity",
            "--output", str(output / ".work/raw"), "--kitti-dataset", str(staged["kitti"]),
            "--maicity-dataset", str(staged["maicity"]), "--kitti-frame-count", "1101", "--maicity-frame-count", "100",
            "--cmake", "cmake", "--build-jobs", "2", "--warmup-runs", "3", "--runs", "10", "--mesh-policy", "quality",
            "--quality-ground-truth", str(output / ".work/maicity_reference.ply"), "--quality-runner", str(runner)]


def run(root: Path) -> None:
    environment_record = environment.preflight(root)
    selected = datasets.sources(root)
    runner = environment.evaluator(root)
    output = root / "results/paper_protocol" / dt.datetime.now().strftime("full_%Y%m%d_%H%M%S_%f")
    raw = output / ".work/raw"
    raw.mkdir(parents=True)
    (raw / "environment.json").write_text(json.dumps(environment_record, indent=2) + "\n")
    comparison_inputs(root, raw)
    staged = datasets.stage(selected, output / ".work")
    prepare_reference(staged["maicity"], output / ".work")
    subprocess.run(protocol_command(root, output, staged, runner), cwd=root, check=True)
    subprocess.run([sys.executable, str(root / "tools/report_protocol.py"), str(raw), "--output", str(output),
                    "--expected-kitti-frames", "1101", "--expected-maicity-frames", "100"], cwd=root, check=True)
    print(f"Validated paper results: {output / 'report.pdf'}")
