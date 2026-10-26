"""Provision a MiMo key over COM7 and run a redacted end-to-end check."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import serial

try:
    import winreg
except ImportError:
    winreg = None


BAUD = 1_000_000
MIMO_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MIMO_MODEL = "mimo-v2.5"
CONFIG_OK = "[ew-ctl] MiMo config saved (key redacted)"
ASK_OK = "[ew-ctl] ask ok:"
ASK_FAIL = "[ew-ctl] ask fail:"


def read_secret(name):
    value = os.environ.get(name, "")
    if value or winreg is None:
        return value
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return ""


def close_serial_apps():
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for image in ("sscom5.exe", "sscom.exe", "putty.exe"):
        subprocess.run(
            ["taskkill", "/F", "/IM", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            check=False,
        )


def collect(sp, seconds):
    chunks = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data = sp.read(4096)
        if data:
            chunks.append(data.decode("utf-8", "replace"))
    return "".join(chunks)


def redact(text, key):
    text = text.replace(key, "<REDACTED>")
    text = re.sub(r"(@mimo-set\s+)\S+", r"\1<REDACTED>", text)
    text = re.sub(r'("api_key"\s*:\s*")[^"]*', r'\1<REDACTED>', text)
    return text


def check_host_connection(key):
    body = json.dumps(
        {
            "model": MIMO_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "In Python, what expression adds 1 and 1? "
                        "Reply only ONLINE if the answer is 2."
                    ),
                }
            ],
            "max_completion_tokens": 128,
            "stream": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        MIMO_URL,
        data=body,
        headers={"api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            response.read()
            return response.status == 200, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return False, f"HTTP {exc.code}: {redact(detail, key)}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, str(exc)


def send_until(sp, command, marker, attempts, wait_seconds):
    transcript = []
    for attempt in range(1, attempts + 1):
        sp.reset_input_buffer()
        sp.write((command + "\r\n").encode("utf-8"))
        text = collect(sp, wait_seconds)
        transcript.append(f"ATTEMPT {attempt}\n{text}")
        if marker in text:
            return True, "\n".join(transcript)
    return False, "\n".join(transcript)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--env", default="MIMO_API_KEY")
    parser.add_argument("--question", default="只回复ONLINE")
    parser.add_argument("--ask-seconds", type=float, default=55.0)
    parser.add_argument(
        "--host-only",
        action="store_true",
        help="verify the Windows-to-MiMo connection without touching the board",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    artifacts = root / "VMware_share" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    log = artifacts / f"mimo_acceptance_{time.strftime('%Y%m%d_%H%M%S')}.txt"

    key = read_secret(args.env)
    if not key:
        message = (
            f"RESULT: FAIL (credential missing: set {args.env} in this process; "
            "do not paste the key into chat)"
        )
        log.write_text(message + "\n", encoding="utf-8")
        print(f"{message}\nLog: {log}")
        return 2
    if len(key) >= 160 or any(ch.isspace() for ch in key):
        message = "RESULT: FAIL (invalid credential shape; key not logged)"
        log.write_text(message + "\n", encoding="utf-8")
        print(f"{message}\nLog: {log}")
        return 2
    if not key.startswith("tp-"):
        message = "RESULT: FAIL (Token Plan credential must start with tp-; key not logged)"
        log.write_text(message + "\n", encoding="utf-8")
        print(f"{message}\nLog: {log}")
        return 2

    host_ok, host_detail = check_host_connection(key)
    if not host_ok:
        message = f"RESULT: FAIL (Windows Token Plan preflight: {host_detail})"
        log.write_text(message + "\n", encoding="utf-8")
        print(f"{message}\nBoard was not modified.\nLog: {log}")
        return 6
    print(f"PASS: Windows Token Plan preflight ({host_detail})")
    if args.host_only:
        message = "RESULT: PASS (Windows Token Plan preflight; board not modified)"
        log.write_text(message + "\n", encoding="utf-8")
        print(f"{message}\nLog: {log}")
        return 0

    close_serial_apps()
    transcript = [
        f"HOST PREFLIGHT: PASS ({host_detail})",
        f"PORT: {args.port} @ {BAUD}, 8N1, RTS/DTR off",
        "KEY: <REDACTED>",
    ]
    try:
        sp = serial.Serial(port=None, baudrate=BAUD, timeout=0.2)
        sp.dtr = False
        sp.rts = False
        sp.port = args.port
        sp.open()
    except serial.SerialException as exc:
        transcript.append(f"OPEN: FAIL: {exc}")
        transcript.append("RESULT: FAIL (serial unavailable)")
        log.write_text("\n".join(transcript) + "\n", encoding="utf-8")
        print(f"FAIL: cannot open {args.port}: {exc}\nLog: {log}")
        return 3

    try:
        configured, config_text = send_until(
            sp, "@mimo-set " + key, CONFIG_OK, attempts=5, wait_seconds=2.5
        )
        transcript.append("CONFIG COMMAND: @mimo-set <REDACTED>")
        transcript.append(redact(config_text, key))
        if not configured:
            transcript.append("RESULT: FAIL (board did not acknowledge MiMo config)")
            log.write_text("\n".join(transcript) + "\n", encoding="utf-8")
            print(f"FAIL: board did not acknowledge config\nLog: {log}")
            return 4

        sp.reset_input_buffer()
        sp.write(("@ask " + args.question + "\r\n").encode("utf-8"))
        ask_text = collect(sp, args.ask_seconds)
        transcript.append("ASK COMMAND: @ask <acceptance question>")
        transcript.append(redact(ask_text, key))
        passed = ASK_OK in ask_text and ASK_FAIL not in ask_text
        transcript.append("RESULT: " + ("PASS" if passed else "FAIL (MiMo request)"))
        log.write_text("\n".join(transcript) + "\n", encoding="utf-8")
        print(("PASS" if passed else "FAIL") + f": MiMo end-to-end check\nLog: {log}")
        return 0 if passed else 5
    finally:
        sp.close()


if __name__ == "__main__":
    sys.exit(main())
