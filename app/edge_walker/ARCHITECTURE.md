# Edge Walker Runtime Boundaries

The application keeps hardware, transport, policy, and presentation separate.
This document is an implementation contract, not a new runtime dependency.

## Ownership

| Module | Owns | Must not do |
|---|---|---|
| `ew_ld2451` | radar framing and approach decision | Wi-Fi, LVGL, Agent calls |
| `alert_*` | LCD, buzzer, and alert output | network requests or radar parsing |
| `ew_wifi_at` | `/dev/ttyS2`, AT serialization, scan/join/HTTP | LVGL object access |
| `ew_net_state` | thread-safe link/error snapshot | AT commands, LVGL, blocking I/O |
| `ew_wifi_ui` | Wi-Fi controls and labels | direct serial access or LLM calls |
| `ew_llm` | MiMo config, HTTP request, result classification | LVGL object access |
| `ew_chat` | chat widgets and user-facing error text | AT commands or credential storage |
| `ew_serial_ctl` | `@` parsing, bounded command queue, routing | bypassing module APIs |
| `ew_mirror` | LCD snapshot framing and transmission | Wi-Fi or input routing |
| `ew_agent*` | Agent skill/tool dispatch | changing radar thresholds |

## Concurrency rules

- LVGL is touched only by the UI loop thread.
- `/dev/ttyS2` is serialized by `ew_wifi_at`; callers never hold its lock while
  touching LVGL.
- `ew_net_state` locks only its own short snapshot update/copy.
- The remote command queue is bounded; drops are logged with secrets redacted.
- Scan, Join, status probes, and HTTPS POST cannot run concurrently on the AT
  device.

## Error flow

`ew_wifi_at` returns transport results. `ew_llm` maps them to `ew_llm_result_t`.
`ew_chat` maps that enum to user text. No layer infers link state from a
credential file; link state comes from `CWJAP?` and `CIPSTA?`.
