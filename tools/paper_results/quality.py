"""Reference/sensitivity quality maps with explicit availability."""
from __future__ import annotations

import json
import math
import shlex
from pathlib import Path

from .common import VARIANTS, read_csv, number
from .quality_maps import colored_ply_extent, render_quality_map
from .latex import render


def reference(source: Path) -> dict:
    row = next(r for r in read_csv(source, "quality.csv") if r.get("variant") == VARIANTS[-1] and r["status"] == "ok")
    directory = source / "quality/maicity_tanks_and_temples" / VARIANTS[-1]
    if not directory.is_dir():
        raise ValueError("Reference quality outputs are missing")
    return {"row": row, "directory": directory}


def sensitivity(source: Path, ref: dict) -> dict:
    candidate = reference(source)
    fields = ("ground_truth", "evaluator_commit", "tau_m", "voxel_size_m", "sample_points")
    if any(candidate["row"][key] != ref["row"][key] for key in fields):
        raise ValueError("Sensitivity and reference use different quality protocols or ground truth")
    ref_metadata = json.loads((ref["directory"].parents[2] / "metadata.json").read_text())
    metadata = json.loads((source / "metadata.json").read_text())
    for key in ("sha256", "frames", "vertices", "poses_sha256", "calibration_sha256"):
        if metadata.get("reference_preparation", {}).get(key) != ref_metadata.get("reference_preparation", {}).get(key):
            raise ValueError(f"Sensitivity reference preparation differs: {key}")
    for key in ("maicity_sequence", "maicity_start_frame", "maicity_frame_count"):
        if metadata["arguments"][key] != ref_metadata["arguments"][key]:
            raise ValueError(f"Sensitivity interval differs: {key}")
    if not metadata.get("finished_at") or metadata["source_git"]["commit"] != ref_metadata["source_git"]["commit"] or metadata["source_git"]["status"]:
        raise ValueError("Sensitivity needs a completed run of the same clean source revision")
    edge = metadata["arguments"].get("max_triangle_dist")
    if edge is None or not math.isclose(float(edge), 0.55):
        raise ValueError("The paper sensitivity run must record max_triangle_dist=0.55")
    command = source / "commands/maicity_reference_pre_scan_polyline_throughput.txt"
    tokens = shlex.split(command.read_text())
    if "--max-triangle-dist" not in tokens or not math.isclose(float(tokens[tokens.index("--max-triangle-dist") + 1]), 0.55):
        raise ValueError("Sensitivity command does not confirm the 0.55 m edge limit")
    return candidate


def map_body(extent: tuple, panels: list[tuple[str, str]], clip: float) -> str:
    xmin, xmax, ymin, ymax = extent
    lines = [r"\begin{tikzpicture}\begin{groupplot}[", r"group style={group size=2 by " + str(len(panels) // 2) + r",horizontal sep=1.05cm,vertical sep=1.15cm},",
             r"scale only axis,width=0.40\linewidth,height=0.27\linewidth,axis equal image,",
             f"xmin={xmin},xmax={xmax},ymin={ymin},ymax={ymax},",
             r"xlabel={$x$ (m)},ylabel={$y$ (m)},tick label style={font=\scriptsize},label style={font=\small},title style={font=\small}]"]
    for title, image in panels:
        lines += [r"\nextgroupplot[title={" + title + "}]",
                  f"\\addplot graphics[xmin={xmin},xmax={xmax},ymin={ymin},ymax={ymax}] {{{image}}};"]
    legend = (Path(__file__).parent / "templates/quality_legend.tex").read_text()
    for key, value in (("MiddleOne", clip / 3), ("MiddleTwo", 2 * clip / 3), ("Clip", clip)):
        legend = legend.replace("\\EvaluationQualityMap" + key, f"{value:.2f}")
    lines += [r"\end{groupplot}\end{tikzpicture}", r"\par\smallskip\centering", legend]
    return "\n".join(lines)


def export(publication, inputs: dict) -> list[dict]:
    if not publication.verification["quality_checked"]:
        publication.item("figure_error_maps", "skipped", "Geometric quality was explicitly omitted for this run.")
        return []
    ref = reference(publication.source)
    if not math.isclose(float(publication.metadata["arguments"].get("max_triangle_dist", 0.30)), 0.30):
        raise ValueError("The reference paper export requires the 0.30 m edge limit")
    candidates = [("reference", ref)]
    extra_rows = []
    automatic = publication.metadata["arguments"].get("include_sensitivity")
    candidate_source = publication.source / "sensitivity" if automatic else inputs.get("sensitivity_results")
    if candidate_source is not None:
        extra = sensitivity(candidate_source, ref)
        candidates.append(("sensitivity", extra))
        extra_rows.append({"method": "RIMBA (0.55 m)", "max_triangle_edge_m": 0.55,
                           **{k + "_percent": 100 * number(extra["row"], k) for k in ("precision", "recall", "f1")},
                           "tau_m": number(extra["row"], "tau_m"), "source": "this run, 0.55 m" if automatic else "archived sensitivity run"})
    paths = [item["directory"] / f"__.{metric}.ply" for _, item in candidates for metric in ("precision", "recall")]
    extent = colored_ply_extent(paths)
    status = "complete" if len(candidates) == 2 else "partial"
    note = "The 0.55 m sensitivity panels were not supplied." if status == "partial" else ""
    publication.item("figure_error_maps", status, note)
    panels, rows = [], []
    clip = 3 * number(ref["row"], "tau_m")
    for variant, item in candidates:
        for metric in ("precision", "recall"):
            name = f"figure_error_maps_{variant}_{metric}.png"
            path = publication.path("figure_error_maps", "png").with_name(name)
            width, height = render_quality_map(item["directory"] / f"__.{metric}.ply", path, extent)
            publication.register("figure_error_maps", path)
            edge = "0.30" if variant == "reference" else "0.55"
            panels.append((metric.title() + ", " + edge + " m", "figures/" + name))
            rows.append({"panel": variant + "_" + metric, "xmin": extent[0], "xmax": extent[1],
                         "ymin": extent[2], "ymax": extent[3], "width": width, "height": height, "clip_m": clip})
    publication.data("figure_error_maps", rows)
    render(publication, "figure_error_maps", map_body(extent, panels, clip))
    return extra_rows
