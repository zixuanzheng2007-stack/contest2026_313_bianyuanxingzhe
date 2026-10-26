#!/usr/bin/env python3
"""Build the dependency-free Android companion with installed SDK/JDK tools.

No Gradle download, global environment change, or device installation occurs.
Outputs and the local debug signing key remain under the ignored output folder.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "mobile/android"


def directory(value: str | None, choices: list[Path], label: str) -> Path:
    candidates = [Path(value)] if value else choices
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError(f"{label} not found; pass its explicit directory")


def source_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        name = path.relative_to(ROOT).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="Android SDK root")
    parser.add_argument("--jdk", help="JDK root containing bin/javac")
    parser.add_argument("--api", type=int, default=35)
    parser.add_argument("--build-tools", default="35.0.0")
    parser.add_argument("--output", type=Path, default=ROOT / "output/mobile_android")
    args = parser.parse_args()
    log = None
    try:
        sdk_choices = [Path(value) for value in (
            os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME"),
            "C:/Program Files (x86)/Android/android-sdk",
        ) if value]
        javac_path = shutil.which("javac")
        jdk_choices = [Path(value) for value in (
            os.environ.get("JAVA_HOME"),
            str(Path(javac_path).parent.parent) if javac_path else None,
            "C:/Program Files (x86)/Android/openjdk/jdk-17.0.14",
        ) if value]
        sdk = directory(args.sdk, sdk_choices, "Android SDK")
        jdk = directory(args.jdk, jdk_choices, "JDK")
        suffix = ".exe" if os.name == "nt" else ""
        tools = sdk / "build-tools" / args.build_tools
        java, javac, keytool = [jdk / "bin" / (name + suffix)
                                for name in ("java", "javac", "keytool")]
        aapt = tools / ("aapt2" + suffix)
        align = tools / ("zipalign" + suffix)
        d8 = tools / "lib/d8.jar"
        signer = tools / "lib/apksigner.jar"
        android_jar = sdk / f"platforms/android-{args.api}/android.jar"
        for path in (java, javac, keytool, aapt, align, d8, signer, android_jar,
                     APP / "AndroidManifest.xml"):
            if not path.is_file():
                raise RuntimeError(f"Required file missing: {path}")
        output = args.output.resolve()
        # Keep local signing material and all generated files out of source.
        if not output.is_relative_to((ROOT / "output").resolve()):
            raise RuntimeError("Output must be inside the project's ignored output/ directory")
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        build = output / ("build-" + stamp + "-" + uuid.uuid4().hex[:8])
        build.mkdir()
        generated, classes, dex = [build / name for name in ("generated", "classes", "dex")]
        for path in (generated, classes, dex):
            path.mkdir()
        log = (build / "build.log").open("w", encoding="utf-8")

        def run(label: str, command: list[object]) -> None:
            print(label, flush=True)
            log.write(f"\n=== {label} ===\n")
            log.flush()
            result = subprocess.run([str(value) for value in command], cwd=ROOT,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=180)
            text = result.stdout.decode("utf-8", errors="replace")
            log.write(text)
            log.flush()
            if result.returncode:
                raise RuntimeError(f"{label} failed ({result.returncode}):\n{text}")

        resource_zip = build / "resources.zip"
        resource_apk = build / "resources.apk"
        run("Compile Android resources", [aapt, "compile", "--dir", APP / "res", "-o", resource_zip])
        run("Link manifest and resources", [aapt, "link", "--manifest", APP / "AndroidManifest.xml",
                                             "-I", android_jar, "--java", generated,
                                             "-o", resource_apk, resource_zip])
        sources = sorted((APP / "src").rglob("*.java")) + sorted(generated.rglob("*.java"))
        if not sources:
            raise RuntimeError("No Java application sources found")
        run("Compile Java", [javac, "--release", "8", "-encoding", "UTF-8",
                             "-classpath", android_jar, "-d", classes, *sources])
        classes_jar = build / "classes.jar"
        with zipfile.ZipFile(classes_jar, "w", compression=zipfile.ZIP_DEFLATED) as jar:
            for path in sorted(classes.rglob("*.class")):
                jar.write(path, path.relative_to(classes).as_posix())
        run("Compile Android bytecode", [java, "-cp", d8, "com.android.tools.r8.D8",
                                          "--min-api", "26", "--lib", android_jar,
                                          "--output", dex, classes_jar])
        unsigned = build / "unsigned.apk"
        shutil.copyfile(resource_apk, unsigned)
        with zipfile.ZipFile(unsigned, "a") as apk:
            for path in sorted(dex.glob("classes*.dex")):
                apk.write(path, path.name, compress_type=zipfile.ZIP_STORED)
        aligned = build / "aligned.apk"
        run("Align APK", [align, "-f", "4", unsigned, aligned])
        # Dated delivery directories must retain the application's signing
        # identity, otherwise adb install -r cannot update the existing app.
        keystore = ROOT / "output/mobile_android/debug.keystore"
        keystore.parent.mkdir(parents=True, exist_ok=True)
        if not keystore.exists():
            run("Create local development signing key", [
                keytool, "-genkeypair", "-noprompt", "-keystore", keystore,
                "-storepass", "android", "-keypass", "android", "-alias", "androiddebugkey",
                "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                "-dname", "CN=Edge Walker Development,O=Edge Walker,C=CN",
            ])
        signed = build / "edge-walker-companion-debug.apk"
        run("Sign development APK", [java, "-jar", signer, "sign", "--ks", keystore,
                                      "--ks-key-alias", "androiddebugkey", "--ks-pass", "pass:android",
                                      "--key-pass", "pass:android", "--out", signed, aligned])
        run("Verify signature", [java, "-jar", signer, "verify", "--verbose", signed])
        run("Verify alignment", [align, "-c", "4", signed])
        source_paths = [path for path in APP.rglob("*") if path.is_file()] + [Path(__file__).resolve()]
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        app_manifest = ET.parse(APP / "AndroidManifest.xml").getroot()
        android_ns = "{http://schemas.android.com/apk/res/android}"
        manifest = {
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "package": app_manifest.get("package"),
            "version": app_manifest.get(android_ns + "versionName"),
            "version_code": app_manifest.get(android_ns + "versionCode"),
            "compile_api": args.api, "build_tools": args.build_tools,
            "signing": "local development key; not a production release",
            "sha256": hashlib.sha256(signed.read_bytes()).hexdigest(),
            "source_sha256": source_digest(source_paths),
            "git_head": git.stdout.strip() if git.returncode == 0 else None,
            "apk_bytes": signed.stat().st_size,
            "build_directory": str(build), "board_tested": False,
        }
        (build / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Publish completion marker last. Failed builds preserve prior delivery.
        publish = output / (".publish-" + uuid.uuid4().hex)
        shutil.copyfile(signed, publish)
        os.replace(publish, output / signed.name)
        manifest_tmp = output / (".manifest-" + uuid.uuid4().hex)
        manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(manifest_tmp, output / "manifest.json")
        print(f"BUILD_OK {output / signed.name}", flush=True)
        print(f"SHA256 {manifest['sha256']}", flush=True)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(f"BUILD_FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        if log is not None:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
