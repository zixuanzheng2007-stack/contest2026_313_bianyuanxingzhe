#!/usr/bin/env python3
"""Read-only checks for one explicitly selected HarmonyOS phone; never install/reset."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdc", type=Path, required=True)
    parser.add_argument("--target", required=True, help="Explicit USB phone target; never a COM port")
    parser.add_argument("--apk", type=Path, required=True, help="Inspect Android package locally; do not install")
    parser.add_argument("--output", type=Path, help="New JSON report, refuses overwrite")
    args = parser.parse_args()
    if not args.target.strip() or args.target.upper().startswith("COM"):
        parser.error("Select one explicit USB phone, not a serial port")
    output = args.output or Path("output/harmony_preflight") / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(3) + ".json")
    if output.exists():
        parser.error("Evidence already exists; choose a new output")
    report = {"scope": "read_only_harmony_phone_preflight", "fixture_state": False,
              "phone_tested": True, "board_tested": False, "ui_tested": False,
              "independent_wireless_tested": False,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "target_sha256_prefix": hashlib.sha256(args.target.encode()).hexdigest()[:12],
              "checks": [], "device": {}}

    def query(*command):
        result = subprocess.run([str(args.hdc.resolve()), "-t", args.target, *command],
                                capture_output=True, timeout=10)
        text = result.stdout.decode("utf-8", errors="replace").strip()
        # HDC may return process code zero even when the remote command fails.
        if result.returncode or not text or "[Fail]" in text or "Get parameter" in text:
            raise RuntimeError("HDC/remote query failed: " + command[-1])
        return text

    exit_code = 2
    try:
        for name, key in (("model", "const.product.model"),
                          ("system", "const.ohos.fullname"),
                          ("software", "const.product.software.version"),
                          ("api", "const.ohos.apiversion")):
            report["device"][name] = query("shell", "param", "get", key)
            report["checks"].append({"id": "phone_" + name, "status": "passed"})
        package_bytes = args.apk.read_bytes()
        with zipfile.ZipFile(args.apk) as package:
            android = "AndroidManifest.xml" in package.namelist() and "classes.dex" in package.namelist()
        report["package"] = {"name": args.apk.name, "sha256": hashlib.sha256(package_bytes).hexdigest(),
                             "android_apk": android}
        native = "Harmony" in report["device"]["system"] and int(report["device"]["api"]) >= 12
        report["preflight_passed"] = True
        if native and android:
            # A native installer refusing APK says nothing about Android
            # compatibility runtimes. Inspect only the user-authorized runtime.
            result = subprocess.run([str(args.hdc.resolve()), "-t", args.target,
                                     "shell", "bm", "dump", "-n", "com.droi.tong"],
                                    capture_output=True, timeout=10)
            text = result.stdout.decode("utf-8", errors="replace")
            try:
                bundle = json.loads(text[text.index("{"):])
                installed = bundle.get("name") == "com.droi.tong"
            except (ValueError, json.JSONDecodeError):
                bundle, installed = {}, False
            report["container"] = {"bundle": "com.droi.tong", "installed": installed,
                                   "version": bundle.get("versionName")}
            report["checks"].append({"id": "package_compatibility", "status": "pending",
                                     "reason": "APK must be imported into the Android container; native HDC install is not this route"})
            report["next_required"] = ("Import APK through installed Droitong and test in that runtime"
                                       if installed else "Confirm availability of the authorized Android compatibility runtime")
        else:
            report["checks"].append({"id": "package_compatibility", "status": "unverified",
                                     "reason": "This preflight never proves application installation or execution"})
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        report["preflight_passed"] = False
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        exit_code = 1
    report["application_acceptance_passed"] = False
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("PREFLIGHT " + ("PASS" if report["preflight_passed"] else "FAIL"))
    print("APPLICATION ACCEPTANCE PENDING: container installation and UI/wireless tests not verified")
    print("REPORT " + str(output.resolve()))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
