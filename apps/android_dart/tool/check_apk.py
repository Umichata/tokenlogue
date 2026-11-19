"""Inspect a built ARM64 APK without executing application code."""

import argparse
import gzip
import hashlib
import json
import os
import re
import struct
import subprocess
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("apk", type=Path)
parser.add_argument("--build-tools", required=True, type=Path)
parser.add_argument("--certificate", required=True)
parser.add_argument("--build-number", required=True, type=int)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def run(name, *parts):
    return subprocess.check_output(
        [str(args.build_tools / name), *map(str, parts)], text=True
    )


def digest(data):
    return hashlib.sha256(data).hexdigest()


def elf_loads(data):
    require(
        data[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", data, 18)[0] == 183,
        "Not AArch64 ELF",
    )
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    require(
        size >= 56 and count > 0 and offset + size * count <= len(data),
        "Malformed program header table",
    )
    loads = []
    for index in range(count):
        typ, _, fileoff, vaddr, _, _, _, align = struct.unpack_from(
            "<IIQQQQQQ", data, offset + index * size
        )
        if typ == 1:
            require(align >= 16384 and not align & (align - 1), "PT_LOAD alignment")
            require((vaddr - fileoff) % 16384 == 0, "PT_LOAD offset")
            loads.append(align)
    require(loads, "Missing PT_LOAD")
    return loads


apk = args.apk
certs = run("apksigner", "verify", "--print-certs", apk)
require(
    re.findall(r"Signer #\d+ certificate SHA-256 digest: ([a-f0-9]{64})", certs)
    == [args.certificate],
    "Unexpected certificate",
)
badging = run("aapt", "dump", "badging", apk)
for field in [
    f"versionCode='{args.build_number}'",
    "name='io.github.umichata.tokenlogue.dart'",
    "versionName='0.1.1'",
    "sdkVersion:'24'",
    "targetSdkVersion:'36'",
    "application-label:'Tokenlogue Dart'",
    "native-code: 'arm64-v8a'",
    "launchable-activity: name='io.github.umichata.tokenlogue.dart.MainActivity'",
]:
    require(field in badging, "Unexpected manifest identity or SDK")
xml = run("aapt", "dump", "xmltree", apk, "AndroidManifest.xml")
for flag in ["allowBackup", "fullBackupContent", "usesCleartextTraffic"]:
    require(re.search(r"android:" + flag + r"\([^\n]+\)=\(type 0x12\)0x0\b", xml), flag)
require(
    "application-debuggable" not in badging and "android:sharedUserId" not in xml,
    "Unexpected debug or shared UID",
)
for pages in ("4", "16"):
    run("zipalign", "-c", "-P", pages, "4", apk)
loads = {}
licenses = {}
prefix = os.fsencode(Path.home()) + b"/"
with zipfile.ZipFile(apk) as archive:
    require(archive.testzip() is None, "CRC")
    names = archive.namelist()
    require(len(names) == len(set(names)), "Duplicate member")
    for name in names:
        lower = name.lower()
        data = archive.read(name)
        require(
            not lower.endswith((".py", ".pyc", ".sqlite", ".jks", ".keystore"))
            and not any(
                x in lower
                for x in [
                    "libpython",
                    "serious_python",
                    "sitepackages.zip",
                    "flet/",
                    "integration_test/",
                ]
            ),
            "Unexpected runtime or private member",
        )
        require(prefix not in data, "Builder home found")
        if name.endswith(".so"):
            require(name.startswith("lib/arm64-v8a/"), "Unexpected ABI")
            loads[name] = elf_loads(data)
    require(
        set(loads) >= {"lib/arm64-v8a/libapp.so", "lib/arm64-v8a/libflutter.so"},
        "Flutter runtime absent",
    )
    notices = gzip.decompress(archive.read("assets/flutter_assets/NOTICES.Z"))
    for name in ("Flutter", "cryptography", "sqflite", "markdown"):
        require(name.encode() in notices, name + " notices absent")
    licenses = {"uncompressed_bytes": len(notices), "sha256": digest(notices)}
report = {
    "result": "PASS",
    "artifact": apk.name,
    "sha256": digest(apk.read_bytes()),
    "bytes": apk.stat().st_size,
    "id": "io.github.umichata.tokenlogue.dart",
    "version": "0.1.1",
    "versionCode": args.build_number,
    "certificate_sha256": args.certificate,
    "minSdk": 24,
    "targetSdk": 36,
    "permissions": re.findall(r"uses-permission: name='([^']+)'", badging),
    "members": len(names),
    "load_alignments": loads,
    "zip_alignment_KiB": [4, 16],
    "notices": licenses,
    "runtime_test_claimed": False,
}
args.output.write_text(json.dumps(report, indent=2) + "\n")
