"""Compose the paper's reference captures and highlighted regions."""
import json
from pathlib import Path
import shutil

from .common import sha256
from .latex import escape, render


def rectangles(boxes, width, height):
    output = []
    for box in boxes:
        x0, x1 = box["x"] / width, (box["x"] + box["width"]) / width
        y0, y1 = 1 - (box["y"] + box["height"]) / height, 1 - box["y"] / height
        output.append(f"\\draw[red!85!black,dashed,line width=.5pt] ({x0:.6f},{y0:.6f}) rectangle ({x1:.6f},{y1:.6f});")
    return " ".join(output)


def compose(publication):
    directory = Path(__file__).parents[2] / "assets/qualitative"
    config = json.loads((directory / "views.json").read_text())
    publication.item("figure_qualitative", "supplied", "Paper reference captures.")
    width, height = config["source_image_size"]
    lines = [r"\begingroup\setlength{\tabcolsep}{1pt}\renewcommand{\arraystretch}{0}",
             r"\newcommand{\RimbaPanel}[2]{\begin{tikzpicture}[baseline=(im.south),inner sep=0,outer sep=0]\node[anchor=south west,inner sep=0,outer sep=0] (im) at (0,0) {\includegraphics[width=.265\linewidth]{#1}};\begin{scope}[x={(im.south east)},y={(im.north west)}]#2\end{scope}\end{tikzpicture}}",
             r"\begin{tabular}{@{}rccc@{}}",
             " & " + " & ".join(r"\shortstack{" + escape(view["dataset"] + " " + view["sequence"]) + r"\\" + escape(view["title"]) + "}" for view in config["views"]) + r" \\[2pt]"]
    provenance = []
    for method in config["methods"]:
        cells = []
        for view in config["views"]:
            relative = view["id"] + "/" + method["id"] + ".png"
            source = directory / relative
            checksum = sha256(source)
            if checksum != config["sha256"][relative]:
                raise ValueError(f"Reference capture checksum differs: {relative}")
            target = publication.path("figure_qualitative", "png").with_name("figure_qualitative_" + view["id"] + "_" + method["id"] + ".png")
            shutil.copyfile(source, target)
            publication.register("figure_qualitative", target)
            cells.append(r"\RimbaPanel{figures/" + target.name + "}{" + rectangles(view["boxes"], width, height) + "}")
            provenance.append({"method": method["label"], "view": view["id"], "sha256": checksum, "source": "paper reference capture", "manuscript_revision": config["provenance"]["manuscript_revision"]})
        lines.append(r"\scriptsize " + escape(method["label"]) + " & " + " & ".join(cells) + r" \\[1pt]")
    lines += [r"\end{tabular}\endgroup"]
    publication.data("figure_qualitative", provenance)
    render(publication, "figure_qualitative", "\n".join(lines))
