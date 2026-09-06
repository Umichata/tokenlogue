"""Obtain one explicitly selected build artifact; never execute its contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY = "Umichata/tokenlogue"
WORKFLOW_PATH = ".github/workflows/build-linux.yml"
API = f"https://api.github.com/repos/{REPOSITORY}"
MAX_ARCHIVE = 2 * 1024**3
APPIMAGE_NAME = re.compile(r"Tokenlogue-(\d+\.\d+\.\d+)-x86_64\.AppImage")


class VerificationError(ValueError):
    """Safe, local explanation, never an API response or credential."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise VerificationError(reason)


def validate_inputs(run_id: str, commit: str, infrastructure_commit: str) -> None:
    require(bool(re.fullmatch(r"[1-9][0-9]{0,19}", run_id)), "invalid source_run_id")
    for sha in (commit, infrastructure_commit):
        require(
            bool(re.fullmatch(r"[0-9a-f]{40}", sha)),
            "full lowercase commit SHA required",
        )


def select_artifact(
    run: dict[str, Any],
    workflow: dict[str, Any],
    artifacts: list[dict[str, Any]],
    run_id: str,
    commit: str,
) -> dict[str, Any]:
    require(run.get("id") == int(run_id), "run ID mismatch")
    require(
        run.get("repository", {}).get("full_name") == REPOSITORY, "wrong repository"
    )
    require(run.get("status") == "completed", "source run is not completed")
    require(run.get("conclusion") == "success", "source run is not successful")
    require(run.get("head_sha") == commit, "source commit mismatch")
    require(workflow.get("path") == WORKFLOW_PATH, "wrong source workflow")
    require(run.get("workflow_id") == workflow.get("id"), "workflow ID mismatch")
    require(run.get("path") == WORKFLOW_PATH, "run workflow path mismatch")
    expected = f"tokenlogue-linux-diagnostic-{commit[:7]}"
    matches = [item for item in artifacts if item.get("name") == expected]
    require(len(matches) == 1, "expected artifact is missing or ambiguous")
    artifact = matches[0]
    require(artifact.get("expired") is False, "source artifact expired")
    require(
        type(artifact.get("id")) is int and artifact["id"] > 0, "invalid artifact ID"
    )
    association = artifact.get("workflow_run", {})
    require(association.get("id") == int(run_id), "artifact run mismatch")
    require(association.get("head_sha") == commit, "artifact source commit mismatch")
    return artifact


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        # Signed artifact blob URLs are supplied by GitHub, not workflow input.
        require(
            urllib.parse.urlsplit(newurl).scheme == "https", "insecure API redirect"
        )
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, token: str):
        require(bool(token), "GitHub token is unavailable")
        self._token = token
        self._opener = urllib.request.build_opener(SafeRedirect())

    def response(self, path: str):
        require(path.startswith("/") and ".." not in path, "invalid API path")
        request = urllib.request.Request(
            API + path,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Tokenlogue-artifact-verifier",
            },
        )
        return self._opener.open(request, timeout=60)

    def json(self, path: str) -> dict[str, Any]:
        with self.response(path) as response:
            value = json.loads(response.read(8 * 1024**2))
        require(isinstance(value, dict), "unexpected GitHub JSON")
        return value

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        result = []
        for page in range(1, 101):
            data = self.json(
                f"/actions/runs/{run_id}/artifacts?per_page=100&page={page}"
            )
            items = data.get("artifacts")
            require(isinstance(items, list), "invalid artifact listing")
            assert isinstance(items, list)
            require(
                all(isinstance(item, dict) for item in items), "invalid artifact entry"
            )
            result.extend(items)
            if len(items) < 100:
                return result
        raise VerificationError("artifact pagination limit exceeded")

    def download(self, artifact_id: int, destination: Path) -> None:
        with self.response(f"/actions/artifacts/{artifact_id}/zip") as response:
            with destination.open("xb") as output:
                size = 0
                while block := response.read(1024**2):
                    size += len(block)
                    require(size <= MAX_ARCHIVE, "artifact archive is too large")
                    output.write(block)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024**2):
            value.update(block)
    return value.hexdigest()


def safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    require(len(members) <= 10000, "too many archive members")
    names: set[str] = set()
    total = 0
    for member in members:
        name = member.filename
        parts = name.rstrip("/").split("/")
        mode = member.external_attr >> 16
        require(
            bool(name)
            and not name.startswith("/")
            and not any(part in ("", ".", "..") for part in parts)
            and not any(char in name for char in ("\\", ":", "\x00"))
            and all(ord(char) >= 32 for char in name),
            "unsafe archive path",
        )
        require(
            stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), "unsafe archive type"
        )
        require(not member.flag_bits & 1, "encrypted archive member")
        require(name.rstrip("/") not in names, "duplicate archive path")
        names.add(name.rstrip("/"))
        total += member.file_size
        require(total <= 4 * MAX_ARCHIVE, "archive expansion limit exceeded")
    return members


def unpack_verified(
    archive_path: Path, destination: Path, commit: str
) -> dict[str, Any]:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "invalid source commit")
    with zipfile.ZipFile(archive_path) as archive:
        members = safe_members(archive)
        images = [m for m in members if m.filename.endswith(".AppImage")]
        sums = [m for m in members if PurePosixPath(m.filename).name == "SHA256SUMS"]
        require(
            len(images) == 1 and len(sums) == 1, "one AppImage and SHA256SUMS required"
        )
        image = images[0]
        original_name = PurePosixPath(image.filename).name
        match = APPIMAGE_NAME.fullmatch(original_name)
        require(match is not None, "unexpected AppImage filename")
        assert match is not None
        require(sums[0].file_size <= 65536, "checksum manifest too large")
        manifest = archive.read(sums[0]).decode("utf-8")
        # The build workflow writes one basename, even when ZIP paths have prefixes.
        require(
            bool(
                re.fullmatch(
                    r"[0-9a-f]{64} [ *]" + re.escape(original_name) + r"\n", manifest
                )
            ),
            "unexpected checksum manifest",
        )
        expected = manifest[:64]
        destination.mkdir(parents=True, exist_ok=True)
        require(not any(destination.iterdir()), "artifact destination must be empty")
        version = match[1]
        filename = f"Tokenlogue-{version}-{commit[:7]}-x86_64.AppImage"
        target = destination / filename
        try:
            with archive.open(image) as source, target.open("xb") as output:
                while block := source.read(1024**2):
                    output.write(block)
            require(digest(target) == expected, "AppImage SHA-256 mismatch")
            target.chmod(0o755)
            (destination / "SHA256SUMS").write_text(
                f"{expected}  {filename}\n", encoding="utf-8"
            )
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return {
        "filename": filename,
        "version": version,
        "sha256": expected,
        "size": target.stat().st_size,
    }


def obtain(
    client: GitHub, run_id: str, commit: str, infrastructure: str, output: Path
) -> dict[str, Any]:
    validate_inputs(run_id, commit, infrastructure)
    run = client.json(f"/actions/runs/{run_id}")
    workflow = client.json("/actions/workflows/build-linux.yml")
    artifact = select_artifact(run, workflow, client.artifacts(run_id), run_id, commit)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-archive-", dir=output) as temp:
        archive = Path(temp) / "artifact.zip"
        client.download(artifact["id"], archive)
        details = unpack_verified(archive, output / "verified", commit)
    details.update(
        source_run_id=run_id,
        artifact_id=artifact["id"],
        source_commit=commit,
        infrastructure_commit=infrastructure,
        repository=REPOSITORY,
        source_artifact_name=artifact["name"],
    )
    (output / "verified" / "provenance.json").write_text(
        json.dumps(details, indent=2) + "\n", encoding="utf-8"
    )
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--infrastructure-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report: dict[str, Any] = {
        "result": "BLOCKED",
        "reason": "source verification not completed",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        details = obtain(
            GitHub(os.environ.get("GH_TOKEN", "")),
            args.run_id,
            args.commit,
            args.infrastructure_commit,
            args.output,
        )
        report.update(result="PASS", reason="source artifact verified", **details)
        outputs = os.environ.get("GITHUB_OUTPUT")
        if outputs:
            with open(outputs, "a", encoding="utf-8") as target:
                target.write(
                    f"sha256={details['sha256']}\nshort_sha={args.commit[:7]}\n"
                )
        return 0
    except VerificationError as error:
        report.update(result="FAIL", reason=str(error))
        return 1
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        report["reason"] = (
            "artifact retrieval or decoding failed; no runtime test performed"
        )
        return 1
    finally:
        (args.output / "source-verification.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as target:
                target.write(
                    "### Source artifact verification\n\n```json\n"
                    + json.dumps(report, indent=2)
                    + "\n```\n"
                )


if __name__ == "__main__":
    raise SystemExit(main())
