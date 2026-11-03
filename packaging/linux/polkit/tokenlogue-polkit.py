#!/usr/bin/python3 -I
"""Строгая разовая установка только известной policy, без sudo из приложения."""

# Проверка выполняется до импортов stdlib, чтобы каталог загрузки не подменил их.
# ruff: noqa: E402
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    raise SystemExit(
        "Run /usr/bin/python3 -I tokenlogue-polkit.py check|install|uninstall"
    )

import argparse
import hashlib
import json
import os
import secrets
import stat
from pathlib import Path

POLICY_NAME = "io.github.umichata.tokenlogue.policy"
POLICY_SHA256 = "6a950d4274d281ab0dff137fe68d3722d7c7872ccd0f897439cf9f6ed3faed53"
DIRECTORY = Path("/usr/share/polkit-1/actions")


def checked_directory() -> int:
    for path in (Path("/usr"), Path("/usr/share"), DIRECTORY.parent, DIRECTORY):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError("Unsafe system policy directory")
    return os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def read_policy(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise RuntimeError("Policy is not a small regular file")
        data = os.read(descriptor, 16385)
        if (
            len(data) != info.st_size
            or hashlib.sha256(data).hexdigest() != POLICY_SHA256
        ):
            raise RuntimeError("Policy SHA-256 does not match this installer")
        return data
    finally:
        os.close(descriptor)


def checked_existing(directory: int) -> os.stat_result | None:
    try:
        info = os.stat(POLICY_NAME, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o644
    ):
        raise RuntimeError("Refusing unexpected existing policy file")
    read_policy(DIRECTORY / POLICY_NAME)
    return info


def run(operation: str, source: Path) -> str:
    if operation != "check" and os.geteuid() != 0:
        raise RuntimeError("Run this explicit install or uninstall step as root")
    directory = checked_directory()
    temporary: str | None = None
    try:
        existing = checked_existing(directory)
        if operation == "check":
            if existing is None:
                raise RuntimeError("Tokenlogue policy is not installed")
            return "verified"
        if operation == "uninstall":
            if existing is None:
                return "already-absent"
            current = os.stat(POLICY_NAME, dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (existing.st_dev, existing.st_ino):
                raise RuntimeError("Policy changed during verification")
            os.unlink(POLICY_NAME, dir_fd=directory)
            os.fsync(directory)
            return "uninstalled"
        data = read_policy(source)
        if existing is not None:
            return "already-installed"
        temporary = f".tokenlogue-policy-{secrets.token_hex(16)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
            os.fchown(descriptor, 0, 0)
            os.fchmod(descriptor, 0o644)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        # link не перезаписывает внезапно появившийся чужой файл.
        os.link(temporary, POLICY_NAME, src_dir_fd=directory, dst_dir_fd=directory)
        os.unlink(temporary, dir_fd=directory)
        temporary = None
        os.fsync(directory)
        checked_existing(directory)
        return "installed"
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "install", "uninstall"))
    parser.add_argument(
        "policy",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent / POLICY_NAME,
    )
    arguments = parser.parse_args()
    try:
        status = run(arguments.operation, arguments.policy)
    except (OSError, RuntimeError) as error:
        print(
            json.dumps({"status": "refused", "reason": str(error)}, ensure_ascii=False)
        )
        return 1
    print(json.dumps({"status": status, "path": str(DIRECTORY / POLICY_NAME)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
