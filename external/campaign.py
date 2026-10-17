"""Run the five paper baselines in cached per-method Docker images."""
import datetime as dt
import os
from pathlib import Path
import shlex

from tools.reproduction import datasets
from tools.reproduction.campaign import destination
from . import environment, images, records, runtime
from .common.case import Case, METHODS, Workload, git, sha256, write_json


def workloads(staged, frame_count):
    return [Workload(dataset, sequence, frame_count or count, staged[dataset] / "sequences" / sequence)
            for dataset, sequences in datasets.COUNTS.items() for sequence, count in sequences.items()
            if (dataset, sequence) != ("maicity", "02")]


def run(root, output=None, frame_count=None, dry_run=False):
    if frame_count is not None and frame_count < 3:
        raise ValueError("External diagnostics need at least 3 frames for method initialization")
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = destination(root, output or root / ".cache/external/runs" / (records.mode(frame_count) + "_" + stamp), frame_count)
    selected = datasets.sources(root, frame_count)
    print("Checking Docker and the pinned method sources...", flush=True)
    setup = environment.preflight(root)
    planned = {kind: output / "datasets" / kind for kind in selected}
    if dry_run:
        for method in METHODS:
            specification = images.recipe(root, method)
            directory = root / ".cache/external/contexts" / specification["key"]
            if images.inspect(specification["tag"]) is None:
                print(shlex.join(images.build_command(specification, directory)))
            for workload in workloads(planned, frame_count):
                case = Case(root, method, workload, output / method / workload.dataset / workload.sequence)
                print(shlex.join(runtime.command(case, case.output / "case.json", {"image_id": specification["tag"]}, "rimba-external-preview", selected[workload.dataset][workload.sequence].values())))
        print("Dry run complete. No builds, reconstructions or output directories created.")
        return
    setup["methods"] = images.prepare(root)
    print("Recording dataset checksums...", flush=True)
    identity = records.input_identity(selected, frame_count)
    staged = datasets.stage(selected, output)
    manifest = {"schema": "rimba-external-campaign-v1", "status": "running", "frame_count": frame_count,
                "started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "experiments_commit": git(root, "rev-parse", "HEAD"),
                "sources": {method: git(root / "external" / method / "source", "rev-parse", "HEAD") for method in METHODS},
                "protocol_sha256": records.protocol(root), "inputs": identity, "environment": setup, "results": [], "result_checksums": {}}
    write_json(output / "campaign.json", manifest)
    for method in METHODS:
        for workload in workloads(staged, frame_count):
            print(f"{method}: {workload.dataset} {workload.sequence}, {workload.frames} frames", flush=True)
            revision = {"source_commit": manifest["sources"][method], "experiments_commit": manifest["experiments_commit"],
                        "image_id": setup["methods"][method]["image_id"], "recipe_sha256": setup["methods"][method]["recipe_sha256"]}
            case = Case(root, method, workload, output / method / workload.dataset / workload.sequence, revision)
            request = case.output / "case.json"
            write_json(request, case.record())
            runtime.run(case, request, setup["methods"][method])
            relative = str((case.output / "result.json").relative_to(output))
            manifest["results"].append(relative)
            manifest["result_checksums"][relative] = sha256(case.output / "result.json")
            write_json(output / "campaign.json", manifest)
    records.cases(output, manifest)
    if identity != records.input_identity(selected, frame_count):
        raise ValueError("Dataset contents changed during the external campaign")
    if manifest["protocol_sha256"] != records.protocol(root) or git(root, "status", "--porcelain") or git(root, "rev-parse", "HEAD") != manifest["experiments_commit"]:
        raise ValueError("Source checkout changed during the external campaign")
    manifest.update(status="complete", finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
    write_json(output / "campaign.json", manifest)
    pointer = records.pointer(root, frame_count)
    temporary = pointer.with_suffix(".tmp")
    write_json(temporary, {"directory": str(output)})
    os.replace(temporary, pointer)
    print(f"External campaign complete: {output}. Run reproduce.py with the same frame interval to assemble the report.")
