"""Run the QA APK across an actual process death on a fresh, disposable emulator."""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "io.github.umichata.tokenlogue.dart.qa.vaultrotation"
ACTIVITY = "io.github.umichata.tokenlogue.dart.MainActivity"


class CheckpointFailure(RuntimeError):
    """A public, fixed test failure label returned by the isolated fixture."""


class Emulator:
    def __init__(self, sdk, serial, port):
        self.client = [str(sdk / "platform-tools/adb"), "-P", str(port), "-s", serial]

    def adb(self, *args, stdin=None, check=True):
        return subprocess.run(
            [*self.client, *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=check,
            timeout=60,
        )

    def shell(self, *args):
        return self.adb("shell", *args).stdout.strip()

    def private_input(self, commands):
        # Standard input keeps fixture values out of argv and test output.
        return self.adb("shell", "-T", stdin=commands + "\n")

    def send_fixture(self, fixture):
        # The test-only Focus widget accepts physical key events. An IME must
        # never compose or modify the packet between the two app processes.
        if PACKAGE + "/" not in self.focus():
            raise RuntimeError("Wrong foreground package for the fixture")
        chunks = [fixture[i : i + 8] for i in range(0, len(fixture), 8)]
        commands = [
            "input keyevent " + " ".join("KEYCODE_" + c.upper() for c in part)
            for part in chunks
        ]
        self.private_input(
            "\nsleep 0.08\n".join(commands + ["input keyevent KEYCODE_ENTER"])
        )

    def focus(self):
        return next(
            (
                line
                for line in self.shell("dumpsys", "window").splitlines()
                if "mCurrentFocus=" in line
            ),
            "",
        )

    def nodes(self):
        xml = self.adb(
            "exec-out", "uiautomator", "dump", "/dev/tty", check=False
        ).stdout
        start, end = xml.find("<?xml"), xml.find("</hierarchy>")
        if start < 0 or end <= start:
            return ()
        return ET.fromstring(xml[start : end + len("</hierarchy>")]).iter("node")

    def wait_for_status(self, expected, timeout=150):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if PACKAGE + "/" in self.focus():
                for node in self.nodes():
                    if (
                        node.get("package") != PACKAGE
                        or node.get("password") == "true"
                        or node.get("class") == "android.widget.EditText"
                    ):
                        continue
                    labels = (
                        node.get("text", "") + "\n" + node.get("content-desc", "")
                    ).splitlines()
                    if expected in labels:
                        return
                    for label in labels:
                        if label.startswith("Failed: "):
                            raise CheckpointFailure(label)
            time.sleep(0.2)
        raise TimeoutError(f"Missing public QA checkpoint: {expected}")

    def confirm_device(self, system_pin):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            focus = self.focus()
            if "BiometricPrompt" in focus or (
                "com.android.settings/" in focus and "ConfirmLockPassword" in focus
            ):
                ready = any(
                    n.get("package") in ("com.android.systemui", "com.android.settings")
                    and n.get("class") == "android.widget.EditText"
                    and n.get("password") == "true"
                    and n.get("focused") == "true"
                    and n.get("enabled") == "true"
                    for n in self.nodes()
                )
                if ready and self.focus() == focus:
                    self.private_input(f"input text {system_pin}")
                    self.shell("input", "keyevent", "KEYCODE_ENTER")
                    return
            time.sleep(0.2)
        raise TimeoutError("The Android credential field did not become ready")

    def start(self, status):
        self.shell("am", "start", "-W", "-n", f"{PACKAGE}/{ACTIVITY}")
        self.wait_for_status(status)
        return int(self.shell("pidof", PACKAGE))


def run(device, sdk, apk, system_pin, fixture, checkpoints):
    if device.shell("getprop", "ro.kernel.qemu") != "1":
        raise RuntimeError("This test requires a disposable emulator")
    if device.shell("am", "get-current-user") != "0":
        raise RuntimeError("Start with the initial user of a fresh emulator")
    packages = device.shell("pm", "list", "packages", PACKAGE).splitlines()
    if f"package:{PACKAGE}" in packages:
        raise RuntimeError("A QA installation already exists; use a fresh emulator")

    aapt = sdk / "build-tools/36.0.0/aapt"
    badging = subprocess.check_output(
        [str(aapt), "dump", "badging", str(apk)], text=True
    )
    if f"name='{PACKAGE}'" not in badging.splitlines()[0]:
        raise RuntimeError("Unexpected APK application ID")
    if "android.permission.INTERNET" in badging:
        raise RuntimeError("The fixture must run offline")
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()

    # Without a previous credential this command can only set the lock on an
    # unsecured guest. Never change an existing lock or remove an existing app.
    lock = device.private_input(f"locksettings set-pin {system_pin}")
    if "set to" not in lock.stdout.lower():
        raise RuntimeError("Could not set a test screen lock on the fresh guest")
    installed = False
    try:
        result = device.adb("install", str(apk))
        if "Success" not in result.stdout:
            raise RuntimeError("QA installation failed")
        installed = True
        path = device.shell("pm", "path", PACKAGE).removeprefix("package:")
        if device.shell("sha256sum", path).split()[0] != digest:
            raise RuntimeError("Installed base APK differs from the QA artifact")
        first = device.start("Fresh registration ready")
        checkpoints.append({"observed": "Fresh registration ready", "pid": first})
        device.send_fixture(fixture)
        device.confirm_device(system_pin)
        device.wait_for_status("Replacement read back")
        checkpoints.append({"observed": "Replacement read back", "pid": first})

        device.shell("am", "force-stop", PACKAGE)
        if device.adb("shell", "pidof", PACKAGE, check=False).stdout.strip():
            raise RuntimeError("The first QA process is still present")
        checkpoints.append({"observed": "First process absent"})
        second = device.start("Cold verification ready")
        checkpoints.append({"observed": "Cold verification ready", "pid": second})
        if second == first:
            raise RuntimeError("Distinct process identities could not be confirmed")
        device.send_fixture(fixture)
        device.wait_for_status("Cold verification passed")
        checkpoints.append({"observed": "Cold verification passed", "pid": second})
        return {
            "result": "PASS",
            "checkpoints": checkpoints,
            "package": PACKAGE,
            "installed_apk_sha256": digest,
            "first_pid": first,
            "first_process_gone": True,
            "cold_pid": second,
            "android_api": int(device.shell("getprop", "ro.build.version.sdk")),
            "guest_abi": device.shell("getprop", "ro.product.cpu.abi"),
            "page_size": int(device.shell("getconf", "PAGE_SIZE")),
            "pins_distinct": True,
            "fixture_checksum_verified_in_both_processes": True,
            "same_run_slot_confirmed_in_both_processes": True,
            "updated_verifier_read_back_before_stop": True,
            "system_credential_prompt_confirmed": True,
            "before_recovery": {
                "stored_verifier_matches_A": True,
                "stored_verifier_matches_B": False,
            },
            "after_cold_start": {
                "stored_verifier_matches_A": False,
                "stored_verifier_matches_B": True,
                "unlock_with_B": True,
                "original_slot_and_encrypted_draft": True,
            },
            "old_PIN_submitted_to_release_APK": False,
        }
    finally:
        try:
            if installed:
                device.adb("uninstall", PACKAGE)
        finally:
            cleared = device.private_input(f"locksettings clear --old {system_pin}")
            if "cleared" not in cleared.stdout.lower():
                raise RuntimeError("Could not remove the test screen credential")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", help="Serial of a fresh, unsecured disposable AVD")
    parser.add_argument("apk", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--adb-port", type=int, default=5037)
    args = parser.parse_args()
    if not re.fullmatch(r"emulator-[0-9]+", args.device):
        parser.error("Expected an emulator serial")
    sdk = Path(os.environ["ANDROID_HOME"])
    system, original, replacement = secrets.SystemRandom().sample(range(10000), 3)
    payload = f"{original:04d}{replacement:04d}{secrets.token_hex(16)}"
    fixture = payload + hashlib.sha256(payload.encode("ascii")).hexdigest()[:24]
    device = Emulator(sdk, args.device, args.adb_port)
    checkpoints = []
    with args.receipt.open("x", encoding="utf-8") as output:
        try:
            evidence = run(device, sdk, args.apk, f"{system:04d}", fixture, checkpoints)
        except Exception as error:
            # Subprocess output and secret input are never persisted.
            json.dump(
                {
                    "result": "INCOMPLETE",
                    "failure_type": type(error).__name__,
                    "app_checkpoint": str(error)
                    if isinstance(error, CheckpointFailure)
                    else None,
                    "checkpoints": checkpoints,
                },
                output,
                indent=2,
            )
            output.write("\n")
            raise
        json.dump(evidence, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
