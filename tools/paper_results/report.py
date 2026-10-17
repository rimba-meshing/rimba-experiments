"""A restrained LaTeX report following the paper's Evaluation sections."""
from __future__ import annotations

import json

import subprocess
from pathlib import Path

from .common import CATALOG, DATASET_LABELS, SECTIONS
from .latex import compile_report, escape

CAPTIONS = {
    "table_quality": "Geometric quality on Mai City. Scores are percentages.",
    "figure_error_maps": "Spatial precision and recall. Grey indicates locations without samples.",
    "figure_qualitative": "Matched qualitative views.",
    "table_runtime": "Processing time per frame (ms). RIMBA values include 95\\% confidence intervals.",
    "figure_frame_time": "Mean time at each frame position for the three scheduling policies.",
    "figure_stage_profile": "Sequential stage attribution (A--D) and residual time.",
    "table_memory": "Peak sequential memory. Tracked allocations, process RSS and VRAM have different scopes.",
    "figure_memory": "Tracked live storage at the end of each frame during sequential execution.",
    "figure_memory_breakdown": "Simultaneous live allocations at the final frame end.",
    "table_scheduling": "Scheduling performance. Times include 95\\% confidence intervals; memory is measured separately.",
    "table_output_effect": "Effect of scheduling on reconstruction size and geometric quality.",
}


def diagnostic(publication) -> bool:
    counts = publication.verification["frame_counts"]
    arguments = publication.metadata["arguments"]
    return counts != {"kitti": 1101, "maicity": 100} or bool(arguments.get("runtime_frame_count")) or any(
        arguments.get(key) != value for key, value in (("kitti_sequence", "07"), ("maicity_sequence", "01"),
                                                     ("kitti_start_frame", 0), ("maicity_start_frame", 0)))


def artifact(item: dict) -> str:
    if "latex" not in item:
        return ""
    kind = item["kind"]
    lines = [f"\\begin{{{kind}}}[H]", r"\centering", item["latex"],
             "\\caption{" + CAPTIONS[item["id"]] + "}", "\\label{" + item["paper_label"] + "}",
             f"\\end{{{kind}}}"]
    if item["status"] in {"partial", "supplied"} and item["note"]:
        lines.append(r"{\footnotesize " + escape(item["note"]) + r"\par}")
    return "\n".join(lines)


def header(publication) -> str:
    arguments = publication.metadata["arguments"]
    sequences = {"MaiCity": arguments["maicity_sequence"], "Kitti": arguments["kitti_sequence"]}
    macros = "\n".join(r"\newcommand{\Evaluation" + key + "Sequence}{" + escape(value) + "}" for key, value in sequences.items())
    counts = "; ".join(f"{DATASET_LABELS[key]} {arguments[key + '_sequence']}: {value} frames" for key, value in publication.verification["frame_counts"].items())
    if arguments.get("include_runtime_sequences"):
        counts += "; KITTI 03/05/06/10: " + (str(arguments["runtime_frame_count"]) + " frames each" if arguments.get("runtime_frame_count") else "full sequences")
    mode = "Diagnostic intervals. " if diagnostic(publication) else ""
    source = publication.metadata["source_git"]["commit"][:12]
    measured = publication.metadata["git"]["commit"][:12]
    root = Path(__file__).parents[2]
    exporter = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--short"], text=True).strip())
    measurement = "\n".join([
        "% Measurement source: " + publication.metadata["source_git"]["commit"],
        "% Measurement experiments: " + publication.metadata["git"]["commit"],
        "% Measurement started: " + publication.metadata["started_at"],
        f"% Repetitions: {arguments['warmup_runs']} warmups, {arguments['runs']} measured",
        "% GPU: " + next(iter(publication.metadata.get("gpu_before", [])), "not recorded"),
    ])
    external = publication.source / "external_campaign.json"
    if external.is_file():
        campaign = json.loads(external.read_text())
        measurement += "\n% External experiments: " + campaign["experiments_commit"]
        measurement += "\n% External adapters SHA-256: " + campaign["protocol_sha256"]
        measurement += "".join("\n% External " + method + ": " + revision for method, revision in campaign["sources"].items())
        measurement += "".join("\n% External image " + method + ": " + image for method, image in campaign.get("images", {}).items())
    reference = publication.metadata.get("reference_preparation")
    if reference:
        measurement += (f"\n% Reference: MaiCity {reference['sequence']}, {reference['frames']} frames, {reference['vertices']} vertices"
                        f"\n% Reference SHA-256: {reference['sha256']}"
                        f"\n% Reference poses SHA-256: {reference['poses_sha256']}"
                        f"\n% Reference calibration SHA-256: {reference['calibration_sha256']}")
    return r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=22mm]{geometry}
\usepackage[T1]{fontenc}
\usepackage{graphicx,booktabs,array,pgfplots,float,caption,needspace,adjustbox}
\usepgfplotslibrary{groupplots}
\pgfplotsset{compat=1.18}
\captionsetup{font=small,labelfont=bf}
\setlength{\parindent}{0pt}
\setlength{\intextsep}{12pt}
""" + macros + "\n% Exporter revision: " + exporter + (" (modified checkout)" if dirty else "") + "\n" + measurement + r"""
\begin{document}
{\Large\bfseries RIMBA - Experimental results\par}
\smallskip
{\footnotesize """ + escape(mode + counts) + r"\par Source: \texttt{" + source + r"}; experiments: \texttt{" + measured + r"}.\par}" + "\n"


def write(publication):
    lines = [header(publication)]
    for section, title in SECTIONS.items():
        space = r"\Needspace{11.5cm}" if section == "scheduling_ablation" else r"\Needspace{5\baselineskip}"
        lines += [space, "\\section{" + title + "}"]
        for key in CATALOG:
            item = publication.items[key]
            if item["section"] != section:
                continue
            body = artifact(item)
            if body:
                lines.append(body)
            elif key == "table_quality":
                lines.append(r"{\small Geometric quality was omitted for this run.\par}")
            elif item["status"] == "requires_input":
                lines.append(r"{\footnotesize " + escape(item["note"]) + r"\par}")
    lines.append(r"\end{document}")
    return compile_report(publication, "\n\n".join(lines) + "\n")
