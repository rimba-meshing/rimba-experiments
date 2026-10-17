"""One fixed-pose reconstruction and its recorded outputs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

METHODS = ("vdbfusion", "puma", "slamesh", "immesh", "cad_mesher")
LABELS = dict(zip(METHODS, ("VDBFusion", "PUMA", "SLAMesh", "ImMesh", "CAD-Mesher")))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@dataclass(frozen=True)
class Workload:
    dataset: str
    sequence: str
    frames: int
    directory: Path

    def record(self) -> dict:
        return {"dataset": self.dataset, "sequence": self.sequence,
                "frames": self.frames, "directory": str(self.directory)}


@dataclass(frozen=True)
class Case:
    root: Path
    method: str
    workload: Workload
    output: Path
    revisions: dict | None = None

    @property
    def source(self) -> Path:
        return self.root / "external" / self.method / "source"

    def record(self) -> dict:
        return {"root": str(self.root), "method": self.method,
                "workload": self.workload.record(), "output": str(self.output), "revisions": self.revisions}


def load_case() -> Case:
    if len(sys.argv) != 2:
        raise ValueError("Expected the campaign-generated reconstruction request")
    data = json.loads(Path(sys.argv[1]).read_text())
    workload = data["workload"]
    request = Workload(workload["dataset"], workload["sequence"], int(workload["frames"]), Path(workload["directory"]))
    if request.frames < 1 or data["method"] not in METHODS:
        raise ValueError("Invalid reconstruction request")
    return Case(Path(data["root"]), data["method"], request, Path(data["output"]), data.get("revisions"))


def mesh_counts(path: Path) -> dict:
    counts = {}
    with path.open("rb") as stream:
        for raw in stream:
            line = raw.decode("ascii").strip()
            if line.startswith("element vertex "):
                counts["vertices"] = int(line.split()[-1])
            elif line.startswith("element face "):
                counts["faces"] = int(line.split()[-1])
            elif line == "end_header":
                break
    if counts.get("vertices", 0) <= 0 or counts.get("faces", 0) <= 0:
        raise ValueError(f"Empty or invalid reconstruction: {path}")
    return counts


def finish(case: Case, mesh: Path, timing: dict, extra: dict | None = None) -> None:
    target = case.output / "mesh.ply"
    if mesh.resolve() != target.resolve():
        shutil.copyfile(mesh, target)
    revisions = case.revisions or {"source_commit": git(case.source, "rev-parse", "HEAD"),
                                   "experiments_commit": git(case.root, "rev-parse", "HEAD")}
    record = {"schema": "rimba-external-case-v1", "method": case.method,
              "workload": case.workload.record(), "mesh": target.name,
              "mesh_sha256": sha256(target), **mesh_counts(target),
              "timing": timing, **revisions, **(extra or {})}
    native = case.output / timing["source"]
    record["native_trace_sha256"] = sha256(native)
    write_json(case.output / "result.json", record)
