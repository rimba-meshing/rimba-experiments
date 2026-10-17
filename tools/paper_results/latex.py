"""Collect manuscript-style LaTeX and compile one report."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess


def require_rendering() -> None:
    for name in ("pdflatex", "kpsewhich"):
        if shutil.which(name) is None:
            raise ValueError(f"Required rendering tool missing: {name}. See README.md#requirements.")
    for package in ("pgfplots.sty", "booktabs.sty", "geometry.sty", "float.sty", "caption.sty", "needspace.sty", "adjustbox.sty"):
        if subprocess.run(["kpsewhich", package], capture_output=True).returncode:
            raise ValueError(f"Missing LaTeX package: {package}. See README.md#requirements.")


def escape(value) -> str:
    mapping = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
               "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(mapping.get(c, c) for c in str(value))


def render(publication, key: str, body: str) -> None:
    publication.items[key]["latex"] = body


def figure(publication, key: str, template: str) -> None:
    path = Path(__file__).parent / "templates" / f"{template}.tex"
    render(publication, key, r"\resizebox{\linewidth}{!}{%" + "\n" + path.read_text() + "}")


def compile_report(publication, source: str) -> Path:
    tex = publication.output / "report.tex"
    tex.write_text(source, encoding="utf-8")
    scratch = publication.output / ".work/latex"
    scratch.mkdir(parents=True, exist_ok=True)
    logs = publication.output / ".work/export_logs"
    logs.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    stamp = dt.datetime.fromisoformat(publication.metadata["started_at"])
    environment.update(SOURCE_DATE_EPOCH=str(int(stamp.timestamp())), FORCE_SOURCE_DATE="1", TZ="UTC")
    command = ["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
               "-output-directory", str(scratch), "report.tex"]
    print("Rendering report.pdf", flush=True)
    log_path = logs / "report.log"
    with log_path.open("w") as log:
        for _ in range(2):
            result = subprocess.run(command, cwd=publication.output, env=environment, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise ValueError(f"LaTeX failed; inspect {log_path}")
    pdf = publication.output / "report.pdf"
    shutil.copyfile(scratch / "report.pdf", pdf)
    return pdf
