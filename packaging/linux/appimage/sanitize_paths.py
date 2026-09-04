"""Replace build-machine paths in staged binary and bytecode files."""

from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path

SERIOUS_PYTHON_TEMP = re.compile(rb"/tmp/serious_python_temp[A-Za-z0-9]{6}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("appdir", type=Path)
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()

    appdir = args.appdir.resolve(strict=True)
    source_root = str(args.source_root.resolve(strict=True)).encode("utf-8")
    source_flutter = source_root + b"/build/flutter"
    if appdir.name != "Tokenlogue.AppDir":
        raise SystemExit("Refusing to sanitize an unexpected AppDir")
    if len(source_root) < len(b"tokenlogue/source/"):
        raise SystemExit("Source root is too short for a stable replacement")

    source_replacement = _same_length_replacement(
        b"tokenlogue/source/", len(source_root)
    )
    source_flutter_replacement = _same_length_replacement(
        b"tokenlogue/flutter/", len(source_flutter)
    )
    changed_files = 0
    source_replacements = 0
    source_flutter_replacements = 0
    temporary_replacements = 0

    for path in sorted(appdir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        source_flutter_count = data.count(source_flutter)
        if source_flutter_count:
            data = data.replace(source_flutter, source_flutter_replacement)
            source_flutter_replacements += source_flutter_count

        source_count = data.count(source_root)
        if source_count:
            data = data.replace(source_root, source_replacement)
            source_replacements += source_count

        temporary_count = len(SERIOUS_PYTHON_TEMP.findall(data))
        if temporary_count:
            data = SERIOUS_PYTHON_TEMP.sub(
                lambda match: _same_length_replacement(
                    b"tokenlogue/app/", len(match.group(0))
                ),
                data,
            )
            temporary_replacements += temporary_count

        if source_flutter_count or source_count or temporary_count:
            _replace_file(path, data)
            changed_files += 1

    for path in sorted(appdir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        if (
            source_root in data
            or b"build/flutter" in data
            or SERIOUS_PYTHON_TEMP.search(data)
        ):
            raise SystemExit(f"Build path remains in staged file: {path}")

    print(f"sanitized_files={changed_files}")
    print(f"source_root_replacements={source_replacements}")
    print(f"source_flutter_replacements={source_flutter_replacements}")
    print(f"serious_python_temp_replacements={temporary_replacements}")


def _same_length_replacement(prefix: bytes, length: int) -> bytes:
    if len(prefix) > length:
        raise ValueError("Replacement prefix does not fit")
    return prefix + b"_" * (length - len(prefix))


def _replace_file(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".sanitize",
            delete=False,
        ) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
