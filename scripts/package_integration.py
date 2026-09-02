#!/usr/bin/env python3
"""Build the deterministic HACS release archive."""

from __future__ import annotations

from pathlib import Path
import stat
from zipfile import ZIP_STORED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components" / "kotlin_ac"
OUTPUT = ROOT / "build" / "kotlin_ac.zip"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def main() -> int:
    files = tuple(
        sorted(
            path
            for path in SOURCE.rglob("*")
            if path.is_file()
            and path.suffix in {".json", ".py"}
            and "__pycache__" not in path.parts
        )
    )
    required = {SOURCE / "__init__.py", SOURCE / "manifest.json"}
    if not required.issubset(files):
        raise FileNotFoundError("Home Assistant integration source is incomplete")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_STORED) as archive:
        for source in files:
            # HACS extracts a zip_release directly into the integration directory.
            # The archive must therefore contain manifest.json at its root rather
            # than another custom_components/kotlin_ac prefix.
            relative = source.relative_to(SOURCE).as_posix()
            info = ZipInfo(relative, FIXED_TIMESTAMP)
            info.create_system = 3
            info.compress_type = ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, source.read_bytes())
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
