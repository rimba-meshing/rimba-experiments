"""Produce reader-facing paper artifacts from validated measurements."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess

from . import analysis, bundle, inputs, quality, report, runtime, tables
from .common import CATALOG, Publication, sha256, write_json
from .latex import figure, require_rendering


def figures(publication: Publication) -> list[dict]:
    publication.item("figure_frame_time", note="Original per-position means across measured executions. No temporal smoothing.")
    for dataset, records in analysis.frame_profiles(publication.source).items():
        publication.data("figure_frame_time", records, f"figure_frame_time_{dataset}.csv")
    figure(publication, "figure_frame_time", "frame_time")
    publication.item("figure_stage_profile", note="Sequential diagnostic scopes grouped by stages A–D. Enclosing timers are never added to nested timers. Residual completes the instrumented total.")
    publication.data("figure_stage_profile", analysis.stage_profiles(publication.source))
    figure(publication, "figure_stage_profile", "stage_profile")
    profiles, summaries, breakdowns = analysis.memory_profiles(publication.source)
    publication.item("figure_memory", note="Measured frame-end live storage during sequential execution. These curves describe reconstruction growth.")
    for dataset, records in profiles.items():
        publication.data("figure_memory", records, f"figure_memory_{dataset}.csv")
    figure(publication, "figure_memory", "memory")
    publication.item("figure_memory_breakdown", note="Simultaneous live allocations at the final measured frame end. Device and host groups are checked against the tracked totals.")
    publication.data("figure_memory_breakdown", breakdowns)
    figure(publication, "figure_memory_breakdown", "memory_breakdown")
    return summaries


def exporter_record() -> dict:
    root = Path(__file__).parents[2]
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    rendering = {}
    for command in (["pdflatex", "--version"],):
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        rendering[command[0]] = (result.stdout or result.stderr).splitlines()[0]
    files = list((root / "tools/paper_results").rglob("*.py")) + list((root / "tools/paper_results/templates").glob("*.tex"))
    return {"repository_commit": git("rev-parse", "HEAD"), "working_tree_status": git("status", "--short"),
            "rendering_tools": rendering,
            "analysis_and_template_hashes": {str(p.relative_to(root)): sha256(p) for p in sorted(files)}}


def provenance(publication: Publication, archive: dict, supplied: dict) -> None:
    environment = publication.source / "environment.json"
    data = {
        "schema": "rimba-paper-results-v1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "diagnostic": report.diagnostic(publication), "measurement": publication.metadata,
        "environment": json.loads(environment.read_text()) if environment.is_file() else None,
        "verification": publication.verification, "exporter": exporter_record(),
        "paper_inputs": supplied.get("manifest"),
        "artifacts": [{k: v for k, v in item.items() if k != "latex"} for item in publication.items.values()], "raw_archive": archive,
        "published_files": [{"path": str(p.relative_to(publication.output)), "bytes": p.stat().st_size, "sha256": sha256(p)}
                            for p in sorted(publication.output.rglob("*")) if p.is_file()
                            and not p.is_relative_to(publication.output / ".work") and p.name not in {"raw.tar.gz", "provenance.json"}],
    }
    write_json(publication.output / "provenance.json", data)


def export(source: Path, output: Path, options) -> Path:
    require_rendering()
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("index.html", "provenance.json", "report.tex", "report.pdf")):
        raise ValueError(f"Publication output already exists: {output}")
    with bundle.open_bundle(source) as raw:
        if output.is_relative_to(raw):
            raise ValueError("The publication destination must be outside the measurement directory")
        publication = Publication(output, raw)
        bundle.validate(publication, options.skip_quality, options.expected_counts)
        input_path = options.paper_inputs or (raw / "publication_inputs.json" if (raw / "publication_inputs.json").is_file() else None)
        supplied = inputs.load(input_path)
        values = analysis.throughput(raw)
        if not publication.verification["quality_checked"]:
            for row in values:
                row["f1_percent"] = ""
        summaries = figures(publication)
        tables.core_tables(publication, values, summaries)
        additional = runtime.records(raw, publication.metadata)
        tables.runtime_table(publication, values, additional + inputs.external_rows(supplied, "runtime"))
        sensitivity_rows = quality.export(publication, supplied)
        tables.quality_table(publication, inputs.external_rows(supplied, "quality") + sensitivity_rows)
        inputs.qualitative(publication, supplied)
        if set(publication.items) != set(CATALOG):
            raise ValueError("Some paper artifacts have no availability record")
        if options.keep_meshes and (raw / "meshes").is_dir():
            shutil.copytree(raw / "meshes", output / "meshes")
        pdf = report.write(publication)
        if options.keep_raw:
            archive = bundle.archive_raw(publication, supplied)
            provenance(publication, archive, supplied)
            bundle.verify_files(output)
    shutil.rmtree(output / ".work")
    print(f"Paper results: {pdf}")
    return pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Legacy measurement directory or paper result bundle.")
    parser.add_argument("--output", type=Path, required=True, help="Destination for the paper outputs.")
    parser.add_argument("--paper-inputs", type=Path, help="Optional JSON describing supplied comparisons and views.")
    parser.add_argument("--keep-meshes", action="store_true")
    parser.add_argument("--keep-raw", action="store_true", help="Retain raw evidence and provenance; omitted by default.")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--expected-kitti-frames", type=int)
    parser.add_argument("--expected-maicity-frames", type=int)
    options = parser.parse_args()
    options.expected_counts = (options.expected_kitti_frames, options.expected_maicity_frames) if options.expected_kitti_frames else None
    if bool(options.expected_kitti_frames) != bool(options.expected_maicity_frames):
        parser.error("Supply both expected frame counts or neither.")
    export(options.bundle.expanduser().resolve(), options.output.expanduser().resolve(), options)
