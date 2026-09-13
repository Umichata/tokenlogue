"""Маленький комплект для внутренних валидаторов. Production pins не изменяются."""

from __future__ import annotations

import copy
import hashlib
import json
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def runtime_elf() -> bytes:
    """Настоящие таблицы ELF64 static PIE без необходимости запускать ELF."""
    names = b"\0.text\0.dynamic\0.digest_md5\0.shstrtab\0"
    code = b"\xb8\x3c\0\0\0\x31\xff\x0f\x05"
    code_offset = 64 + 2 * 56
    dynamic_offset = code_offset + len(code)
    dynamic = struct.pack("<qQqQ", 0x6FFFFFFB, 0x08000000, 0, 0)
    md5_offset = dynamic_offset + len(dynamic)
    names_offset = md5_offset + 16
    section_offset = names_offset + len(names)
    size = section_offset + 5 * 64
    identity = b"\x7fELF\x02\x01\x01\0AI\x02" + b"\0" * 5
    header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        identity,
        3,
        62,
        1,
        code_offset,
        64,
        section_offset,
        0,
        64,
        56,
        2,
        64,
        5,
        4,
    )
    programs = struct.pack("<IIQQQQQQ", 1, 5, 0, 0, 0, size, size, 4096)
    programs += struct.pack(
        "<IIQQQQQQ",
        2,
        6,
        dynamic_offset,
        dynamic_offset,
        0,
        len(dynamic),
        len(dynamic),
        8,
    )
    sections = bytes(64)
    for name, kind, flags, offset, length in [
        (".text", 1, 6, code_offset, len(code)),
        (".dynamic", 6, 3, dynamic_offset, len(dynamic)),
        (".digest_md5", 1, 2, md5_offset, 16),
        (".shstrtab", 3, 0, names_offset, len(names)),
    ]:
        sections += struct.pack(
            "<IIQQQQIIQQ",
            names.index(name.encode()),
            kind,
            flags,
            offset,
            offset,
            length,
            0,
            0,
            1,
            0,
        )
    return header + programs + code + dynamic + bytes(16) + names + sections


class RuntimeFixture:
    def __init__(self, root: Path):
        self.root = root
        self.lock = json.loads(
            (ROOT / "packaging/linux/appimage/runtime-artifact.lock.json").read_text()
        )
        self.notice_lock = json.loads(
            (ROOT / "packaging/linux/appimage/notices.lock.json").read_text()
        )
        self.files: dict[str, bytes] = {"runtime-x86_64": runtime_elf()}
        self.lock["runtime_size"] = len(self.files["runtime-x86_64"])
        self.lock["runtime_sha256"] = sha(self.files["runtime-x86_64"])
        workflow = "materials/recipe/.github/workflows/build-appimage-runtime.yml"
        self.files[workflow] = b"name: fixture\non:\n  workflow_dispatch:\n"
        recipe_files = [
            {
                "path": ".github/workflows/build-appimage-runtime.yml",
                "sha256": sha(self.files[workflow]),
                "size": len(self.files[workflow]),
                "mode": 0o644,
            }
        ]
        self.lock["recipe_fingerprint"] = sha(
            json.dumps(recipe_files, sort_keys=True).encode()
        )
        components = []
        inputs = []
        linked = []
        for index, (name, spec) in enumerate(self.lock["components"].items()):
            source_name = f"sources/{name}.tar.gz"
            data = ("Исходный fixture " + name).encode()
            self.files["materials/inputs/" + source_name] = data
            inputs.append(
                {
                    "path": source_name,
                    "size": len(data),
                    "sha256": sha(data),
                    "url": self.notice_lock["runtime"]["components"][name]["source"],
                }
            )
            component = {
                "name": name,
                "source": source_name,
                "licenses": [f"{name}/{n}" for n in spec["licenses"]],
            }
            if name == "type2-runtime":
                component["commit"] = spec["version"]
            elif name in {"libfuse", "squashfuse"}:
                component["version"] = spec["version"]
            else:
                component["package_version"] = spec["version"]
                component["aports_commit"] = "d" * 40
            components.append(component)
            for filename in spec["licenses"]:
                self.files[f"materials/licenses/{name}/{filename}"] = (
                    f"Copyright © fixture {name}. License: unchanged; original text.\n".encode()
                )
            archive_name = f"{index:02d}-{name}.a"
            contents = ("!<arch>\n" + name).encode()
            self.files[f"materials/linked-inputs/build-one/{archive_name}"] = contents
            entry = {
                "component": name,
                "size": len(contents),
                "sha256": sha(contents),
                "saved_as": "linked-inputs/" + archive_name,
                "linker_path": "/build-one/private/" + archive_name,
                "resolved_path": "/home/runner/private/" + archive_name,
            }
            if "aports_commit" in component:
                entry["package"] = {
                    "origin": name,
                    "version": spec["version"],
                    "aports_commit": component["aports_commit"],
                }
            linked.append(entry)
        build_lock = {
            "upstream": {"commit": self.lock["upstream_commit"]},
            "components": components,
            "files": inputs,
        }
        self.files["runtime.lock.json"] = encoded(build_lock)
        self.lock["runtime_lock_sha256"] = sha(self.files["runtime.lock.json"])
        coverage = {"result": "PASS", "unresolved": [], "files": linked}
        self.files["reports/build-one/linked-inputs.json"] = encoded(coverage)
        checks = {
            stage: {"result": "PASS", "recipe_sha256": self.lock["recipe_fingerprint"]}
            for stage in (
                "fetch",
                "prepare",
                "build-one",
                "build-two",
                "compare",
                "verify",
                "smoke",
            )
        }
        checks["prepare"].update(apk_signatures="PASS", inventory="PASS")
        identity = {
            "sha256": self.lock["runtime_sha256"],
            "size": self.lock["runtime_size"],
        }
        for stage in ("build-one", "build-two"):
            checks[stage].update(identity)
        checks["compare"].update(byte_identical=True, builds=[identity, identity])
        checks["smoke"].update(
            runtime_sha256=self.lock["runtime_sha256"],
            new_runtime_prefix="PASS",
            extract="PASS",
            extract_and_run="PASS",
            argument_marker="PASS",
        )
        for stage, check in checks.items():
            self.files[f"reports/reports/{stage}.json"] = encoded(check)
        self.manifest = {
            "schema": 1,
            "result": "PASS",
            "runtime": {"path": "runtime-x86_64", **identity},
            "upstream_source_commit": self.lock["upstream_commit"],
            "tokenlogue_recipe": {
                "commit": self.lock["producer_commit"],
                "sha256": self.lock["recipe_fingerprint"],
                "dirty": False,
                "files": recipe_files,
            },
            "source_materials": "REVIEW_REQUIRED: Flutter SDK",
            "checks": checks,
            "runtime_source_materials": coverage,
            "files": [
                {"path": name, "size": len(data), "sha256": sha(data)}
                for name, data in self.files.items()
            ],
        }
        self.files["manifest.json"] = encoded(self.manifest)
        self.files["SHA256SUMS"] = "".join(
            f"{sha(data)}  {name}\n" for name, data in sorted(self.files.items())
        ).encode()
        self.notice_lock["runtime"].update(
            sha256=self.lock["runtime_sha256"],
            bytes=self.lock["runtime_size"],
            recipe_fingerprint=self.lock["recipe_fingerprint"],
            runtime_lock_sha256=self.lock["runtime_lock_sha256"],
        )
        self.archive, self.lock = self.write_zip(self.files)
        self.notice_lock["runtime"].update(
            archive_sha256=self.lock["archive_sha256"],
            manifest_sha256=self.lock["manifest_sha256"],
        )

    def write_zip(
        self,
        files: dict[str, bytes],
        *,
        duplicate: str | None = None,
        symlink: str | None = None,
    ) -> tuple[Path, dict]:
        archive = self.root / "runtime.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as target:
            for name, data in files.items():
                member = zipfile.ZipInfo(name)
                member.external_attr = (0o120777 if name == symlink else 0o100644) << 16
                target.writestr(member, data)
            if duplicate is not None:
                target.writestr(duplicate, files[duplicate])
        lock = copy.deepcopy(self.lock)
        lock["archive_size"] = archive.stat().st_size
        lock["archive_sha256"] = sha(archive.read_bytes())
        lock["manifest_sha256"] = sha(files["manifest.json"])
        return archive, lock

    def api(self) -> tuple[dict, dict, dict]:
        lock = self.lock
        run = {
            "id": lock["source_run_id"],
            "run_attempt": lock["run_attempt"],
            "head_sha": lock["producer_commit"],
            "repository": {"full_name": lock["repository"]},
            "workflow_id": 123,
            "path": lock["workflow"],
            "status": "completed",
            "conclusion": "success",
        }
        workflow = {"id": 123, "path": lock["workflow"]}
        artifact = {
            "id": lock["artifact_id"],
            "name": lock["artifact_name"],
            "size_in_bytes": lock["archive_size"],
            "digest": "sha256:" + lock["archive_sha256"],
            "expired": False,
            "expires_at": "2099-09-27T00:00:00Z",
            "workflow_run": {
                "id": lock["source_run_id"],
                "head_sha": lock["producer_commit"],
            },
        }
        return run, workflow, artifact
