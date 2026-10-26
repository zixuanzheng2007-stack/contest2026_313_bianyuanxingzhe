#!/usr/bin/env python3
"""Exercise existing radar-alert, buzzer, display, and mirror interfaces."""

from __future__ import annotations

from serial_common import artifact_path, open_port, receive, send_line, write_log


def main() -> int:
    log_path = artifact_path("stage2_peripheral_acceptance")
    transcript = ["Stage-2 peripheral acceptance",
                  "port=COM7 baud=1000000 dtr=0 rts=0"]
    with open_port() as port:
        transcript.append(receive(port, 1.0))
        for command, wait in (
            ("@goto warn", 2.0),
            ("@fake 1.0 40.0", 3.0),
            ("@alert soft stage2-soft", 3.0),
            ("@alert strong stage2-strong", 3.0),
            ("@alert none stage2-clear", 3.0),
            ("@mirror snap", 9.0),
        ):
            transcript.extend((f">>> {command}", send_line(port, command, wait)))

    text = "\n".join(transcript)
    write_log(log_path, text)
    checks = {
        "radar decision path": "[ew-ctl] fake 1.0m 40.0km/h" in text,
        "alert output path": text.count("[alert_output] level=") >= 3,
        "buzzer worker path": "[ew-buzz] alert worker" in text,
        "LCD alert path": "[alert_lcd] display level=" in text,
        "display mirror 390x450": "[ew-mirror] frame 390x450" in text,
    }
    print(f"LOG={log_path}")
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    passed = all(checks.values())
    print(f"VERDICT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
