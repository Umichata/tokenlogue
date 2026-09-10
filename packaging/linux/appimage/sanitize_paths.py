"""Replace build-machine paths in staged binary and bytecode files."""

from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path

SERIOUS_PYTHON_TEMP = re.compile(rb"/tmp/serious_python_temp[A-Za-z0-9]{6}")
SECRET_TOKEN = re.compile(
    rb"sk-or-v1-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
)
PRIVATE_KEY = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _raise_walk_error(error: OSError) -> None:
    raise error


def _regular_files(root: Path) -> Iterator[Path]:
    for directory, directories, names in os.walk(root, onerror=_raise_walk_error):
        directories.sort()
        for name in sorted(names):
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                continue  # validate_symlinks checks every link before this scan.
            if not stat.S_ISREG(mode):
                raise SystemExit(f"Unexpected staged file: {path.relative_to(root)}")
            yield path


def check_staged_contents(
    appdir: Path, source_root: bytes, *, check_secrets: bool = False
) -> None:
    for path in _regular_files(appdir):
        data = path.read_bytes()
        if any(
            pattern in data
            for pattern in (
                source_root,
                b"build/flutter",
                b"/home/runner",
                b"/tmp/serious_python_temp",
            )
        ):
            raise SystemExit(
                f"Build path remains in staged file: {path.relative_to(appdir)}"
            )
        if check_secrets and (
            SECRET_TOKEN.search(data)
            or not data.startswith(b"\x7fELF")
            and PRIVATE_KEY.search(data)
        ):
            raise SystemExit(
                f"Secret-like data in staged file (values omitted): {path.relative_to(appdir)}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("appdir", type=Path)
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="verify paths and secret patterns without edits",
    )
    args = parser.parse_args()

    appdir = args.appdir.resolve(strict=True)
    source_root = str(args.source_root.resolve(strict=True)).encode("utf-8")
    source_flutter = source_root + b"/build/flutter"
    if appdir.name != "Tokenlogue.AppDir":
        raise SystemExit("Refusing to sanitize an unexpected AppDir")
    if args.check_only:
        check_staged_contents(appdir, source_root, check_secrets=True)
        print("Staged content checks: PASS")
        return
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

    for path in _regular_files(appdir):
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

    check_staged_contents(appdir, source_root)

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
