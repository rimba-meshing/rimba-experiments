"""Build and identify the cached Docker image for each external method."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from .common.case import METHODS, git, sha256, write_json
from .common.process import execute

ROS_METHODS = {"slamesh", "immesh", "cad_mesher"}


def recipe(root, method):
    family = "ros" if method in ROS_METHODS else method
    docker = root / "external/docker"
    files = {"Dockerfile": docker / (family + ".Dockerfile"), "inventory.py": docker / "inventory.py"}
    if method in ROS_METHODS:
        files["build_ros.py"] = docker / "build_ros.py"
        files.update({"patches/" + p.name: p for p in sorted((root / "external/patches" / method).glob("*.patch"))})
    else:
        files["requirements.txt"] = root / "external" / method / "requirements.txt"
    if method == "vdbfusion":
        files["FindOpenVDB.cmake"] = docker / "FindOpenVDB.cmake"
    source = root / "external" / method / "source"
    record = {"schema": "rimba-external-image-v1", "method": method, "source_commit": git(source, "rev-parse", "HEAD"),
              "files": {name: sha256(path) for name, path in files.items()}}
    key = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return {"record": record, "files": files, "key": key, "tag": "rimba-external-" + method + ":" + key[:20]}


def inspect(tag):
    result = subprocess.run(["docker", "image", "inspect", tag], capture_output=True, text=True)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def build_command(specification, context):
    command = ["docker", "build", "--progress=plain", "--label", "org.rimba.recipe=" + specification["key"],
               "--label", "org.rimba.method=" + specification["record"]["method"], "--tag", specification["tag"]]
    if specification["record"]["method"] in ROS_METHODS:
        command += ["--build-arg", "METHOD=" + specification["record"]["method"]]
    return command + [str(context)]


def context(root, specification):
    path = root / ".cache/external/contexts" / specification["key"]
    if path.exists():
        return path
    path.mkdir(parents=True)
    for name, source in specification["files"].items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (path / "patches").mkdir(exist_ok=True)
    (path / "source").mkdir()
    source = root / "external" / specification["record"]["method"] / "source"
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar", "--output=" + str(path / "source.tar"), "HEAD"], check=True)
    subprocess.run(["tar", "-xf", str(path / "source.tar"), "-C", str(path / "source")], check=True)
    (path / "source.tar").unlink()
    write_json(path / "build-input.json", {**specification["record"], "recipe_sha256": specification["key"]})
    return path


def prepare(root):
    methods = {}
    for method in METHODS:
        specification = recipe(root, method)
        image = inspect(specification["tag"])
        if image is None:
            print(f"Building {method} image (first use)...", flush=True)
            directory = context(root, specification)
            log = root / ".cache/external/images" / specification["key"] / "build.log"
            execute(build_command(specification, directory), log, root)
            image = inspect(specification["tag"])
        if image is None or image["Config"].get("Labels", {}).get("org.rimba.recipe") != specification["key"]:
            raise ValueError(f"Docker image does not match its recipe: {specification['tag']}")
        command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "cat", image["Id"], "/opt/environment.json"]
        inventory = json.loads(subprocess.check_output(command, text=True))
        if inventory["build"]["recipe_sha256"] != specification["key"]:
            raise ValueError("Image build inventory does not match the selected sources")
        methods[method] = {"tag": specification["tag"], "image_id": image["Id"], "recipe_sha256": specification["key"],
                           "source_commit": specification["record"]["source_commit"], "inventory": inventory}
    return methods
