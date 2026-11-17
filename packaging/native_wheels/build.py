"""Compile the pinned dependency wheels, separately from application packaging."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
SOURCE_EPOCH = "1794913200"
VERSIONS = {
    "setuptools": "83.0.0",
    "wheel": "0.43.0",
    "build": "1.2.2.post1",
    "packaging": "24.2",
    "pyproject-hooks": "1.2.0",
}
SOURCES = {
    "cffi": (
        "packaging/android/crypto/sources/cffi-2.0.0.tar.gz",
        "44d1b5909021139fe36001ae048dbdde8214afa20200eda0f64c068cac5d5529",
    ),
    "pycryptodomex": (
        "packaging/android/crypto/sources/pycryptodomex-3.23.0.tar.gz",
        "71909758f010c82bc99b0abf4ea12012c98962fbf0583c2164f8b84533c2e4da",
    ),
    "msgpack": (
        "packaging/native_wheels/sources/msgpack-1.1.2.tar.gz",
        "3b60763c1373dd60f398488069bcdc703cd08a711477b5d480eecc9f9626f47e",
    ),
    "libffi": (
        "packaging/native_wheels/sources/libffi-3.4.4.tar.gz",
        "d66c56ad259a82cf2a9dfc408b32bf5da52371500b84745f7fb8b645712df676",
    ),
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_tree(name: str, work: Path) -> Path:
    relative, expected = SOURCES[name]
    archive = PROJECT / relative
    if sha(archive) != expected:
        raise ValueError(f"Pinned source mismatch {name}")
    destination = work / name
    destination.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")
    children = list(destination.iterdir())
    if len(children) != 1 or not children[0].is_dir():
        raise ValueError("Unexpected source archive layout")
    return children[0]


def run(command: list[str], cwd: Path, env: dict[str, str], log: Path) -> None:
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"command": command}) + "\n")
        stream.flush()
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False,
        )
        stream.write(json.dumps({"exit_code": result.returncode}) + "\n")
    if result.returncode:
        raise RuntimeError(f"Native dependency command failed, see {log.name}")


def compiler_environment(work: Path, target: str, ndk: Path | None) -> dict[str, str]:
    flags = "-O2 -fPIC"
    for original, replacement in (
        (Path.home(), "/usr/src/build-host"),
        (work, "/usr/src/native-wheels"),
        (Path(sys.base_prefix), "/usr/src/build-python"),
    ):
        flags += f" -ffile-prefix-map={original}={replacement}"
        flags += f" -fdebug-prefix-map={original}={replacement}"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(work / "home"),
        "LANG": "C.UTF-8",
        "TMPDIR": str(work / "tmp"),
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": SOURCE_EPOCH,
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CFLAGS": flags,
        "CXXFLAGS": flags,
    }
    if target == "linux":
        env["CC"], env["CXX"] = "gcc", "g++"
        env["CFLAGS"] += " -march=x86-64 -mtune=generic"
        env["CXXFLAGS"] += " -march=x86-64 -mtune=generic"
    else:
        if ndk is None:
            raise ValueError("Android requires the pinned NDK")
        properties = (ndk / "source.properties").read_text(encoding="utf-8")
        if "Pkg.Revision = 28.2.13676358" not in properties:
            raise ValueError("Android NDK revision differs from the recipe")
        tools = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
        env.update(
            CC=str(tools / "aarch64-linux-android24-clang"),
            CXX=str(tools / "aarch64-linux-android24-clang++"),
            AR=str(tools / "llvm-ar"),
            RANLIB=str(tools / "llvm-ranlib"),
            STRIP=str(tools / "llvm-strip"),
            NDK_HOME=str(ndk),
            ANDROID_HOME=str(ndk.parents[1]),
            ANDROID_SDK_ROOT=str(ndk.parents[1]),
        )
    return env


def build_libffi(work: Path, target: str, env: dict[str, str], log: Path) -> Path:
    source = source_tree("libffi", work)
    prefix = work / "libffi-prefix"
    if target == "android":
        for name in ("libffi-long_double.patch", "libffi-open_temp_exec_file.patch"):
            run(
                [
                    "patch",
                    "--batch",
                    "--forward",
                    "--fuzz=0",
                    "-p1",
                    "-i",
                    str(HERE / "patches" / name),
                ],
                source,
                env,
                log,
            )
    command = [
        str(source / "configure"),
        f"--prefix={prefix}",
        "--disable-shared",
        "--enable-static",
        "--with-pic",
        "--disable-docs",
        "--disable-multi-os-directory",
    ]
    if target == "android":
        command += ["--host=aarch64-linux-android", "--build=x86_64-pc-linux-gnu"]
    run(command, source, env, log)
    run(["make", "-j4"], source, env, log)
    run(["make", "install"], source, env, log)
    return prefix


def android_python(work: Path, archive: Path, env: dict[str, str], log: Path) -> Path:
    if (
        sha(archive)
        != "b96189c126ca96e7e2b3875747a0bb6db53d651499bfa7463cbb644e27da9f7d"
    ):
        raise ValueError("Android Python support checksum mismatch")
    support = work / "support"
    support.mkdir()
    prefix = "install/android/arm64-v8a/python-3.12.14/"
    with tarfile.open(archive) as source:
        for member in source:
            if member.isfile() and member.name.startswith(prefix):
                relative = Path(member.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe support archive path")
                target = support / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = source.extractfile(member)
                if stream is None:
                    raise ValueError("Unreadable Python support member")
                target.write_bytes(stream.read())
                target.chmod(member.mode)
    host = support / prefix
    configs = list((host / "lib/python3.12").glob("_sysconfigdata*.py"))
    if len(configs) != 1:
        raise ValueError("Ambiguous Android sysconfig")
    run(
        [
            sys.executable,
            "-m",
            "crossenv",
            "--without-pip",
            "--sysconfigdata-file",
            str(configs[0]),
            str(host / "bin/python3.12"),
            str(work / "cross"),
        ],
        work,
        env,
        log,
    )
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("uv0.12.8 is required to seed the isolated build environment")
    version = subprocess.check_output([uv, "--version"], text=True)
    if not version.startswith("uv 0.12.8 "):
        raise ValueError("Pinned uv version differs")
    run(
        [
            uv,
            "pip",
            "sync",
            "--python",
            str(work / "cross/build/bin/python"),
            "--no-index",
            "--require-hashes",
            "--find-links",
            str(HERE / "sources/build-tools"),
            str(HERE / "build-requirements.txt"),
        ],
        work,
        env,
        log,
    )
    return work / "cross/cross/bin/python"


def build_component(
    name: str,
    work: Path,
    target: str,
    python: Path,
    prefix: Path,
    env: dict[str, str],
    log: Path,
) -> Path:
    source = source_tree(name, work)
    if name == "cffi":
        patch = HERE / "patches" / f"cffi-{target}.patch"
    elif name == "pycryptodomex" and target == "android":
        patch = (
            PROJECT
            / "packaging/android/crypto/recipes/recipes/pycryptodomex/patches/mobile.patch"
        )
    else:
        patch = None
    if patch:
        run(
            ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch)],
            source,
            env,
            log,
        )
    environment = dict(env)
    environment.update(
        CPPFLAGS=f"-I{prefix}/include",
        LDFLAGS=f"-L{prefix}/lib",
        PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"),
        PKG_CONFIG_PATH=str(prefix / "lib/pkgconfig"),
    )
    if target == "android":
        support = work / "support/install/android/arm64-v8a/python-3.12.14"
        environment["LDFLAGS"] += (
            f" -L{support}/lib -Wl,-z,max-page-size=16384 -Wl,--build-id=sha1 -lm -lpython3.12"
        )
        environment["LDSHARED"] = (
            environment["CC"] + " -shared " + environment["LDFLAGS"]
        )
        environment["_PYTHON_HOST_PLATFORM"] = "android-24-arm64-v8a"
    if name == "cffi":
        map_argument = f" -Wl,-Map={work / 'cffi-link.map'}"
        environment["LDFLAGS"] += map_argument
        if target == "android":
            environment["LDSHARED"] += map_argument
    output = work / "unpacked-wheels"
    output.mkdir(exist_ok=True)
    run(
        [
            str(python),
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--outdir",
            str(output),
        ],
        source,
        environment,
        log,
    )
    matches = list(output.glob(name + "-*.whl"))
    if len(matches) != 1:
        raise ValueError("Unexpected compiled wheel count")
    return matches[0]


def pack_wheel(
    wheel: Path, work: Path, output: Path, target: str, env: dict[str, str], log: Path
) -> None:
    package = wheel.name.split("-")[0]
    unpack = work / f"pack-{package}"
    run(
        [sys.executable, "-m", "wheel", "unpack", "-d", str(unpack), str(wheel)],
        work,
        env,
        log,
    )
    tree = next(unpack.iterdir())
    if package == "cffi":
        info = next(tree.glob("*.dist-info")) / "licenses/libffi"
        info.mkdir(parents=True)
        with tarfile.open(PROJECT / SOURCES["libffi"][0]) as source:
            stream = source.extractfile("libffi-3.4.4/LICENSE")
            if stream is None:
                raise ValueError("Original libffi notice missing")
            (info / "LICENSE").write_bytes(stream.read())
        names = (
            ["libffi-long_double.patch", "libffi-open_temp_exec_file.patch"]
            if target == "android"
            else []
        )
        declaration = {
            "component": "libffi",
            "version": "3.4.4",
            "source_archive": "libffi-3.4.4.tar.gz",
            "source_sha256": SOURCES["libffi"][1],
            "linkage": "static",
            "patches": [
                {"filename": name, "sha256": sha(HERE / "patches" / name)}
                for name in names
            ],
            "role": "libffi compiled for this CFFI wheel. Separate from the CPython runtime libffi.",
        }
        (info / "BUILD.json").write_text(
            json.dumps(declaration, indent=2) + "\n", encoding="utf-8"
        )
    run(
        [
            sys.executable,
            "-m",
            "wheel",
            "pack",
            "--build-number",
            "1001",
            "--dest-dir",
            str(output),
            str(tree),
        ],
        work,
        env,
        log,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("android", "linux"), required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--support-archive", type=Path)
    parser.add_argument("--ndk", type=Path)
    args = parser.parse_args()
    if sys.version_info[:3] != (3, 12, 14):
        parser.error("CPython3.12.14 is required")
    for package, expected in VERSIONS.items():
        if importlib.metadata.version(package) != expected:
            parser.error(f"Pinned build dependency differs {package}")
    work = args.work_dir.absolute()
    if work.exists() or work.parent.resolve() not in {Path("/tmp"), Path("/var/tmp")}:
        parser.error("Use a new physical workspace directly under /tmp or /var/tmp")
    if args.output.exists():
        parser.error("Output directory already exists")
    if args.platform == "linux":
        libc, version = platform.libc_ver()
        if libc != "glibc" or tuple(map(int, version.split("."))) > (2, 35):
            parser.error(
                "Linux wheels must be compiled inside the Ubuntu22.04 baseline"
            )
    elif args.support_archive is None or args.ndk is None:
        parser.error("Android requires the exact support archive and NDK")
    work.mkdir(mode=0o700)
    for name in ("home", "tmp"):
        (work / name).mkdir()
    args.output.mkdir(parents=True)
    log = args.output / "native-build.log"
    env = compiler_environment(work, args.platform, args.ndk)
    python = Path(sys.executable)
    if args.platform == "android":
        if args.support_archive is None:
            raise ValueError("Android Python support missing")
        python = android_python(work, args.support_archive, env, log)
    prefix = build_libffi(work, args.platform, env, log)
    packages = ["cffi", "pycryptodomex"] + (
        ["msgpack"] if args.platform == "android" else []
    )
    for package in packages:
        wheel = build_component(package, work, args.platform, python, prefix, env, log)
        pack_wheel(wheel, work, args.output, args.platform, env, log)
    inventory = [
        {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}
        for path in sorted(args.output.glob("*.whl"))
    ]
    (args.output / "built-wheels.json").write_text(
        json.dumps({"platform": args.platform, "wheels": inventory}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
