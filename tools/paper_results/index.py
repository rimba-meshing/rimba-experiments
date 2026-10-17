"""A self-contained reader index that follows the paper's Evaluation section."""
from __future__ import annotations

import csv
import base64
from html import escape

from .common import CATALOG, SECTIONS, DATASET_LABELS
from .tables import HEADERS, display

STYLE = """
:root{color-scheme:light;font:16px/1.6 system-ui,sans-serif;color:#23313b;background:#f3f5f7}
*{box-sizing:border-box}body{margin:0}main{max-width:1200px;margin:auto;padding:40px 28px 70px}
header{background:#123b48;color:white;padding:40px;border-radius:12px}h1{font:700 36px/1.2 Georgia,serif;margin:8px 0 20px}
h2{font:700 28px Georgia,serif;margin:40px 0 18px}h3{font:700 21px Georgia,serif;margin:0 0 8px}
header p{max-width:850px;margin:8px 0;color:#dce8ea}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:12px}
nav{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}a{color:#12677a;text-underline-offset:3px}nav a{background:white;padding:8px 14px;border-radius:6px}
.summary{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.chip{padding:5px 12px;background:white;border-radius:6px}
.artifact{background:white;border:1px solid #dce2e7;border-radius:8px;margin:16px 0;padding:24px}
.badge{display:inline-block;padding:3px 9px;font-size:12px;border-radius:4px;background:#e5f3ee;color:#145f46;margin:0 0 12px}
.partial,.requires_input{background:#fff2d8;color:#80540a}.skipped{background:#edf0f3;color:#586875}.supplied{background:#e5edfa;color:#2f558b}
.note{color:#52636f;margin:8px 0 18px;font-size:14px}.links{display:flex;gap:12px;flex-wrap:wrap;font-size:14px}.preview{width:100%;max-height:650px;object-fit:contain;margin:14px 0}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;margin:16px 0}th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #e3e9ed;white-space:nowrap}th{background:#f3f6f8}
footer{margin-top:40px;font-size:13px;color:#657581}details{margin-top:14px;font-size:13px}code{font-size:12px;overflow-wrap:anywhere}
@media(max-width:650px){main{padding:16px}header{padding:24px}h1{font-size:28px}.artifact{padding:16px}}
"""
STATUS = {"complete": "Generated", "partial": "Partially reproduced", "requires_input": "Additional input needed",
          "skipped": "Omitted", "supplied": "Provided input"}


def table_preview(publication, item: dict) -> str:
    path = publication.output / item["section"] / (item["id"] + ".csv")
    if not path.is_file() or "columns" not in item:
        return ""
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    columns = item["columns"]
    heads = "".join("<th>" + escape(HEADERS.get(c, c)) + "</th>" for c in columns)
    body = "".join("<tr>" + "".join("<td>" + escape(display(row, c)) + "</td>" for c in columns) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table></div>'


def card(publication, item: dict) -> str:
    key = item["id"]
    if not item["files"]:
        return f'''<details class="artifact"><summary><span class="badge {item['status']}">{STATUS[item['status']]}</span>
<strong>{escape(item['title'])}</strong></summary><p class="note">{escape(item['note'])}</p></details>'''
    links = "".join(f'<a href="{escape(p, quote=True)}">{escape(p.rsplit("/",1)[-1])}</a>' for p in item["files"])
    svg = publication.output / ".work/previews" / f"{key}.svg"
    image = ""
    if svg.is_file() and item["kind"] == "figure":
        uri = "data:image/svg+xml;base64," + base64.b64encode(svg.read_bytes()).decode()
        image = f'<img class="preview" src="{uri}" alt="{escape(item["title"], quote=True)}">'
    return f'''<article class="artifact" id="{key}">
<span class="badge {item['status']}">{item['kind'].title()} · {STATUS[item['status']]}</span>
<h3>{escape(item['title'])}</h3><p class="note">{escape(item['note'])}</p>
{table_preview(publication,item)}{image}<div class="links">{links}</div>
<details><summary>Paper reference</summary><code>{escape(item['paper_label'])}</code></details></article>'''


def diagnostic(publication) -> bool:
    counts = publication.verification["frame_counts"]
    arguments = publication.metadata["arguments"]
    return counts != {"kitti": 1101, "maicity": 100} or any(
        arguments.get(key) != value for key, value in (("kitti_sequence", "07"), ("maicity_sequence", "01"),
                                                     ("kitti_start_frame", 0), ("maicity_start_frame", 0)))


def write(publication) -> None:
    meta = publication.metadata
    mode = "Diagnostic interval" if diagnostic(publication) else "Full sequence intervals"
    disclaimer = "Short intervals exercise the pipeline. These values are not full-sequence paper results." if diagnostic(publication) else "Times and memory reflect this machine and run."
    chips = [f"{DATASET_LABELS[d]}: {n} frames" for d, n in publication.verification["frame_counts"].items()]
    chips += [f"{publication.verification['throughput_samples']} throughput samples",
              "Quality evaluated" if publication.verification["quality_checked"] else "Quality omitted"]
    summary = "".join('<span class="chip">' + escape(text) + '</span>' for text in chips)
    navigation = "".join(f'<a href="#{key}">{title}</a>' for key, title in SECTIONS.items())
    sections = "".join(f'<section id="{section}"><h2>{title}</h2>' +
                       "".join(card(publication, publication.items[key]) for key in CATALOG if publication.items[key]["section"] == section) + '</section>'
                       for section, title in SECTIONS.items())
    source = escape(meta["source_git"]["commit"])
    experiment = escape(meta["git"]["commit"])
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RIMBA · Paper results</title><style>{STYLE}</style><main>
<header><div class="eyebrow">RIMBA · Reproduction results</div><h1>Evaluation results</h1>
<p><strong>{mode}</strong> · {disclaimer}</p><p>The sections below follow the Evaluation section of the manuscript.
Generated outputs, supplied comparisons, and missing inputs are identified separately.</p></header>
<div class="summary">{summary}</div><nav>{navigation}</nav>{sections}
<footer><h2>Reproducibility record</h2><p>Raw measurements and logs are preserved in one archive.
The provenance record contains input/output checksums, software revisions, and validation results.</p>
<p><a href="provenance.json">Provenance and artifact inventory</a> · <a href="raw.tar.gz">Raw evidence archive</a></p>
<p>Source <code>{source}</code><br>Experiments <code>{experiment}</code></p></footer></main></html>'''
    (publication.output / "index.html").write_text(html, encoding="utf-8")
