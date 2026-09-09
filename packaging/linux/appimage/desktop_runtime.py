"""Keep the host desktop ABI together and probe its modules with AppRun's paths."""

from __future__ import annotations

import argparse
import ctypes
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

# GTK loads the host's IM modules, GIO modules and accessibility integration.
# An older private GLib must not replace their distribution's runtime. Include
# the core dependencies which newer host GLib/GIO/D-Bus may require as well.
HOST_DESKTOP_PATTERNS = (
    "libglib-2.0.so.*",
    "libgobject-2.0.so.*",
    "libgmodule-2.0.so.*",
    "libgthread-2.0.so.*",
    "libgio-2.0.so.*",
    "libgtk-3.so.*",
    "libgdk-3.so.*",
    "libgdk_pixbuf-2.0.so.*",
    "libatk-1.0.so.*",
    "libatk-bridge-2.0.so.*",
    "libatspi.so.*",
    "libpango*.so.*",
    "libcairo*.so.*",
    "libmount.so.*",
    "libblkid.so.*",
    "libselinux.so.*",
    "libpcre2-*.so.*",
    "libffi.so.*",
    "libdbus-1.so.*",
    "libsystemd.so.*",
)


def is_host_desktop_library(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in HOST_DESKTOP_PATTERNS)


def bundled_desktop_libraries(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink()) and is_host_desktop_library(path.name)
    )


def discover_modules() -> dict[str, list[Path]]:
    # Ubuntu multiarch and Fedora lib64. Do not inspect HOME or app storage.
    roots = (Path("/usr/lib/x86_64-linux-gnu"), Path("/usr/lib64"), Path("/usr/lib"))
    patterns = {
        "gio": "gio/modules/*.so",
        "ibus": "gtk-3.0/3.0.0/immodules/im-ibus.so",
        "xapp": "gtk-3.0/modules/libxapp-gtk3-module.so",
    }
    return {
        group: sorted({path.resolve() for root in roots for path in root.glob(pattern)})
        for group, pattern in patterns.items()
    }


def loaded_desktop_libraries() -> list[Path]:
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith("/"):
            path = Path(fields[5])
            if is_host_desktop_library(path.name):
                paths.add(path.resolve())
    return sorted(paths)


def probe_modules(appdir: Path) -> dict[str, object]:
    """Resolve symbols eagerly without starting the application or a GUI."""
    errors: list[str] = []
    handles = []
    modules = discover_modules()
    if not any(path.name == "libgvfsdbus.so" for path in modules["gio"]):
        errors.append("required GVfs GIO module is absent")
    if not modules["ibus"]:
        errors.append("required IBus GTK3 module is absent")
    records = []
    targets = ["libgtk-3.so.0", "libgio-2.0.so.0"]
    targets.extend(str(path) for group in modules.values() for path in group)
    for target in targets:
        try:
            handles.append(ctypes.CDLL(target, mode=os.RTLD_NOW | os.RTLD_GLOBAL))
            records.append({"library": target, "result": "PASS"})
        except OSError as error:
            records.append({"library": target, "result": "FAIL", "reason": str(error)})
            errors.append(f"cannot load {target}")
    loaded = loaded_desktop_libraries()
    for path in loaded:
        if path.is_relative_to(appdir):
            errors.append(f"desktop runtime resolved inside AppDir: {path.name}")
    return {
        "result": "FAIL" if errors else "PASS",
        "method": "dlopen RTLD_NOW with AppRun library paths; no application launch",
        "errors": errors,
        "modules": records,
        "loaded_desktop_libraries": [str(path) for path in loaded],
    }


def run_probe(appdir: Path, report_path: Path) -> int:
    report: dict[str, object] = {"result": "FAIL", "errors": ["probe did not complete"]}
    try:
        appdir = appdir.resolve(strict=True)
        copies = bundled_desktop_libraries(appdir)
        if copies:
            report["errors"] = ["host desktop libraries were bundled", *copies]
        else:
            environment = os.environ.copy()
            # Match AppRun exactly, including remaining private dependencies.
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(
                (str(appdir / "usr/lib"), str(appdir / "usr/lib/tokenlogue/lib"))
            )
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "_probe", str(appdir)],
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if result.returncode == 0:
                decoded = json.loads(result.stdout)
                if not isinstance(decoded, dict) or decoded.get("result") not in (
                    "PASS",
                    "FAIL",
                ):
                    raise ValueError("module probe returned an invalid report")
                report = decoded
            else:
                report["errors"] = [f"module probe exited with {result.returncode}"]
            report["stderr"] = result.stderr
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["errors"] = [str(error)]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["result"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("exclusions")
    check = commands.add_parser("check")
    check.add_argument("appdir", type=Path)
    probe = commands.add_parser("probe")
    probe.add_argument("appdir", type=Path)
    probe.add_argument("--report", type=Path, required=True)
    child = commands.add_parser("_probe")
    child.add_argument("appdir", type=Path)
    args = parser.parse_args()
    if args.command == "exclusions":
        print("\n".join(HOST_DESKTOP_PATTERNS))
    elif args.command == "check":
        copies = bundled_desktop_libraries(args.appdir.resolve(strict=True))
        if copies:
            print(
                "host desktop libraries were bundled: " + ", ".join(copies),
                file=sys.stderr,
            )
            return 1
    elif args.command == "probe":
        return run_probe(args.appdir, args.report)
    else:
        print(json.dumps(probe_modules(args.appdir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
