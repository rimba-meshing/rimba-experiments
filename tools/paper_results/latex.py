"""Render standalone figures from the manuscript's PGFPlots definitions."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess


def require_rendering() -> None:
    for name in ("pdflatex", "pdftocairo", "kpsewhich"):
        if shutil.which(name) is None:
            raise ValueError(f"Required rendering tool missing: {name}. See README.md#requirements.")
    for package in ("standalone.sty", "pgfplots.sty", "booktabs.sty"):
        result = subprocess.run(["kpsewhich", package], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Missing LaTeX package: {package}. See README.md#requirements.")


def escape(value) -> str:
    mapping = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
               "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(mapping.get(c, c) for c in str(value))


def document(body: str, sequences: dict) -> str:
    return r"""\documentclass[border=8pt]{standalone}
\usepackage{graphicx,booktabs,array,pgfplots}
\usepgfplotslibrary{groupplots}
\pgfplotsset{compat=1.18}
""" + "\n".join(r"\newcommand{\Evaluation" + name + "Sequence}{" + escape(value) + "}"
                      for name, value in sequences.items()) + r"""
\begin{document}
\begin{minipage}{14cm}
""" + body + r"""
\end{minipage}
\end{document}
"""


def render(publication, key: str, body: str) -> None:
    directory = publication.path(key, "pdf").parent
    sources = publication.output / ".work/export_sources"
    sources.mkdir(parents=True, exist_ok=True)
    tex = sources / f"{key}.tex"
    sequences = {"MaiCity": publication.metadata["arguments"]["maicity_sequence"],
                 "Kitti": publication.metadata["arguments"]["kitti_sequence"]}
    tex.write_text(document(body, sequences))
    scratch = publication.output / ".work/latex" / key
    scratch.mkdir(parents=True, exist_ok=True)
    logs = publication.output / ".work/export_logs"
    logs.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    stamp = dt.datetime.fromisoformat(publication.metadata["started_at"])
    environment.update(SOURCE_DATE_EPOCH=str(int(stamp.timestamp())), FORCE_SOURCE_DATE="1", TZ="UTC")
    command = ["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
               "-output-directory", str(scratch), str(tex)]
    print(f"Rendering {key}", flush=True)
    with (logs / f"{key}.log").open("w") as log:
        for _ in range(2):
            result = subprocess.run(command, cwd=directory, env=environment, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise ValueError(f"LaTeX failed for {key}; inspect {logs / (key + '.log')}")
    pdf = publication.path(key, "pdf")
    shutil.copyfile(scratch / f"{key}.pdf", pdf)
    preview(publication, key, pdf)
    publication.register(key, pdf)
    if publication.items[key]["kind"] == "table":
        fragment = publication.path(key, "tex")
        fragment.write_text(body)
        publication.register(key, fragment)


def preview(publication, key: str, pdf: Path) -> Path:
    directory = publication.output / ".work/previews"
    directory.mkdir(parents=True, exist_ok=True)
    svg = directory / f"{key}.svg"
    subprocess.run(["pdftocairo", "-svg", str(pdf), str(svg)], check=True)
    return svg


def figure(publication, key: str, template: str) -> None:
    path = Path(__file__).parent / "templates" / f"{template}.tex"
    render(publication, key, path.read_text())
