"""Archive raw evidence and reopen either legacy or publication bundles."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from .common import read_csv, sha256, write_json


@contextmanager
def open_bundle(path: Path):
    path = path.expanduser().resolve()
    if path.is_dir() and (path / "metadata.json").is_file():
        yield path
        return
    archive = path / "raw.tar.gz" if path.is_dir() else path
    if not archive.is_file():
        raise ValueError(f"No measurement manifest or raw archive at {path}")
    if path.is_dir():
        verify_files(path)
    with tempfile.TemporaryDirectory(prefix="rimba-paper-") as temporary:
        with tarfile.open(archive) as stream:
            stream.extractall(temporary, filter="data")
        root = Path(temporary) / "raw"
        if not (root / "metadata.json").is_file():
            raise ValueError("The raw archive has no measurement manifest")
        if path.is_dir():
            provenance = json.loads((path / "provenance.json").read_text())
            for record in provenance["raw_archive"]["files"]:
                file = root / record["path"]
                if not file.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Invalid raw evidence path")
                if not file.is_file() or sha256(file) != record["sha256"]:
                    raise ValueError(f"Raw evidence hash mismatch: {record['path']}")
        yield root


def verify_files(root: Path) -> dict:
    data = json.loads((root / "provenance.json").read_text())
    if data.get("schema") != "rimba-paper-results-v1":
        raise ValueError("Unknown publication bundle schema")
    for record in data["published_files"]:
        path = root / record["path"]
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid published path")
        if not path.is_file() or sha256(path) != record["sha256"]:
            raise ValueError(f"Published artifact hash mismatch: {record['path']}")
    if sha256(root / "raw.tar.gz") != data["raw_archive"]["sha256"]:
        raise ValueError("Raw archive checksum differs from provenance")
    return data


def validate(publication, skip_quality: bool = False, counts: tuple | None = None) -> dict:
    source = publication.source
    arguments = publication.metadata["arguments"]
    rows = read_csv(source, "results.csv")
    frames = {d: int(next(r["frame_count"] for r in rows if r["dataset"] == d)) for d in ("kitti", "maicity")}
    expected = dict(zip(("kitti", "maicity"), counts)) if counts else frames
    output = publication.output / ".work/verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).parents[1] / "check_protocol.py"), str(source),
               "--expected-kitti-frames", str(expected["kitti"]), "--expected-maicity-frames", str(expected["maicity"]),
               "--expected-warmups", str(arguments["warmup_runs"]), "--expected-runs", str(arguments["runs"]),
               "--output", str(output)]
    if skip_quality or arguments.get("skip_quality"):
        command.append("--skip-quality")
    subprocess.run(command, check=True)
    publication.verification = json.loads(output.read_text())
    return publication.verification


def input_entries(publication, inputs: dict) -> list:
    entries, manifest = [], {}
    for key in ("external_quality", "external_runtime"):
        if key in inputs:
            relative = f"paper_inputs/{key}.csv"
            entries.append((inputs[key], relative))
            manifest[key] = relative
    if "qualitative_pdf" in inputs:
        record = inputs["qualitative_pdf"]
        relative = "paper_inputs/qualitative.pdf"
        entries.append((record["file"], relative))
        manifest["qualitative_pdf"] = {"file": relative, "source": record["source"]}
    if "sensitivity_results" in inputs:
        root = inputs["sensitivity_results"]
        if publication.output.is_relative_to(root):
            raise ValueError("The publication destination must be outside the sensitivity directory")
        manifest["sensitivity_results"] = "paper_inputs/sensitivity"
        entries.extend((p, "paper_inputs/sensitivity/" + str(p.relative_to(root))) for p in root.rglob("*") if p.is_file())
    if manifest:
        path = publication.output / ".work/publication_inputs.json"
        write_json(path, manifest)
        entries.append((path, "publication_inputs.json"))
    return entries


def archive_raw(publication, inputs: dict) -> dict:
    archive = publication.output / "raw.tar.gz"
    records = []
    ignored = {"report", "qualitative"}
    print("Archiving raw evidence", flush=True)
    with tarfile.open(archive, "w:gz", compresslevel=1) as stream:
        for path in sorted(publication.source.rglob("*")):
            relative = path.relative_to(publication.source)
            if not path.is_file() or relative.parts[0] in ignored | {"paper_inputs"} or str(relative) in {"external_comparison.csv", "README.md", "publication_inputs.json"}:
                continue
            if path.is_symlink():
                raise ValueError(f"Raw evidence must not contain symbolic links: {relative}")
            record = {"path": str(relative), "bytes": path.stat().st_size, "sha256": sha256(path)}
            stream.add(path, arcname="raw/" + str(relative), recursive=False)
            records.append(record)
        for path, relative in input_entries(publication, inputs):
            if path.is_symlink():
                raise ValueError("Supplied paper evidence must not contain symbolic links")
            stream.add(path, arcname="raw/" + relative, recursive=False)
            records.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
        for name in ("export_logs", "export_sources", "previews"):
            for path in sorted((publication.output / ".work" / name).glob("*")):
                stream.add(path, arcname=name + "/" + path.name, recursive=False)
        stream.add(publication.output / ".work/verification.json", arcname="export_logs/verification.json")
    return {"file": archive.name, "sha256": sha256(archive), "bytes": archive.stat().st_size,
            "files": records, "omitted_legacy_scaffolding": ["report/", "qualitative/", "external_comparison.csv", "README.md"]}
