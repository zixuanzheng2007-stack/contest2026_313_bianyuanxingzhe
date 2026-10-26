#!/usr/bin/env python3
"""Verify panel alert commands drive the expected LCD colors on the board."""

from __future__ import annotations

from serial_common import artifact_path, open_port, receive, send_line, write_log


def main() -> int:
    log_path = artifact_path("alert_color_acceptance")
    transcript = ["Alert color acceptance", "port=COM7 baud=1000000 dtr=0 rts=0"]
    with open_port() as port:
        transcript.append(receive(port, 1.0))
        for command in (
            "@goto warn",
            "@alert soft panel-soft",
            "@alert strong panel-strong",
            "@alert crit panel-crit",
            "@alert none panel-clear",
        ):
            transcript.extend((f">>> {command}", send_line(port, command, 3.0)))

    text = "\n".join(transcript)
    write_log(log_path, text)
    checks = {
        "soft yellow": "rgb=c9a227 text=SOFT reason=panel-soft" in text,
        "strong orange": "rgb=ff8c00 text=WARN reason=panel-strong" in text,
        "crit red": "rgb=ff0000 text=CRIT reason=panel-crit" in text,
    }
    print(f"LOG={log_path}")
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    verdict = all(checks.values())
    print(f"VERDICT={'PASS' if verdict else 'FAIL'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
