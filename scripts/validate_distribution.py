#!/usr/bin/env python3
"""Validate public distribution metadata without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'(?m)^version:\s*"(?P<value>[0-9]+\.[0-9]+\.[0-9]+)"\s*$')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    arguments = parser.parse_args()

    repository = (ROOT / "repository.yaml").read_text()
    config = (ROOT / "kotlin_climate_brain" / "config.yaml").read_text()
    manifest = json.loads(
        (ROOT / "custom_components" / "kotlin_ac" / "manifest.json").read_text()
    )
    match = VERSION.search(config)
    if match is None:
        raise ValueError("app version must be a stable semantic version")
    version = match.group("value")
    if arguments.tag is not None and arguments.tag != f"v{version}":
        raise ValueError("release tag does not match app version")
    if manifest.get("version") != version:
        raise ValueError("integration and app versions differ")
    if "url: https://github.com/frantic777/climatecontroller-ha" not in repository:
        raise ValueError("repository metadata does not point at the public distribution")
    if 'image: "ghcr.io/frantic777/climatecontroller"' not in config:
        raise ValueError("app image is not the approved public GHCR package")
    if manifest.get("documentation") != "https://github.com/frantic777/climatecontroller-ha":
        raise ValueError("integration documentation URL is invalid")
    if manifest.get("issue_tracker") != "https://github.com/frantic777/climatecontroller-ha/issues":
        raise ValueError("integration issue tracker URL is invalid")

    public_text = "\n".join(
        path.read_text(errors="replace")
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )
    if re.search(r"(?:ghp_|github_pat_|Bearer\s+)[A-Za-z0-9_]", public_text):
        raise ValueError("credential-like content found in public distribution")
    print(f"version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

