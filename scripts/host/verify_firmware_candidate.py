# SPDX-License-Identifier: Apache-2.0
"""Verify an ARM firmware image against its ELF and active board configuration.

This is an offline delivery check. It opens no serial device and proves no
physical behavior. The flash address is derived from file-backed PT_LOAD data,
not from an example in a flashing script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

FLASH_BASE = 0x12010000
REQUIRED_CONFIG = (
    "CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER",
    "CONFIG_BSP_USING_UART2", "CONFIG_BSP_UART2_RX_USING_DMA",
    "CONFIG_BSP_USING_UART3", "CONFIG_BSP_UART3_RX_USING_DMA",
    "CONFIG_LCD_USING_CO5300", "CONFIG_INPUT_FT6146",
    "CONFIG_LV_USE_NUTTX", "CONFIG_LV_USE_NUTTX_TOUCHSCREEN",
    "CONFIG_I2C", "CONFIG_I2C_DRIVER",
)
REQUIRED_SYMBOLS = (
    "ew_safety_start", "ew_safety_snapshot", "ew_snapshot_format",
    "ew_serial_ctl_start", "ew_agent_emit_decision_event",
)
AGENT_SYMBOL = "tool_approach_alert_execute"
AGENT_CONFIG = "CONFIG_EXAMPLES_AI_AGENT_VELA"


def _slice(data: bytes, offset: int, length: int) -> bytes:
    if offset < 0 or length < 0 or offset + length > len(data):
        raise ValueError("Truncated ELF data")
    return data[offset:offset + length]


def inspect_elf(data: bytes) -> tuple[int, list[dict], set[str]]:
    if data[:7] != b"\x7fELF\x01\x01\x01" or len(data) < 52:
        raise ValueError("Expected ELF32 little-endian executable")
    header = struct.unpack("<16sHHIIIIIHHHHHH", data[:52])
    _, kind, machine, version, entry, phoff, shoff, _, _, phsize, phcount, shsize, shcount, _ = header
    if (kind, machine, version) != (2, 40, 1) or phsize != 32 or shsize != 40:
        raise ValueError("Expected an ARM executable with standard ELF32 tables")
    loads = []
    for index in range(phcount):
        segment = struct.unpack("<IIIIIIII", _slice(data, phoff + index * phsize, phsize))
        seg_kind, offset, vaddr, paddr, size, memory_size, flags, _ = segment
        if seg_kind != 1 or size == 0:
            continue  # BSS reserves RAM and contributes no bytes to the image.
        if size > memory_size:
            raise ValueError("Invalid file-backed load size")
        _slice(data, offset, size)
        loads.append(dict(offset=offset, vaddr=vaddr, paddr=paddr, size=size, flags=flags))
    if not loads:
        raise ValueError("ELF has no file-backed load segments")
    sections = [struct.unpack("<IIIIIIIIII", _slice(data, shoff + i * shsize, shsize))
                for i in range(shcount)]
    symbols = set()
    for section in sections:
        _, section_kind, _, _, offset, size, link, _, _, entry_size = section
        if section_kind != 2:  # SHT_SYMTAB, including local symbols.
            continue
        if entry_size != 16 or size % entry_size or link >= len(sections):
            raise ValueError("Invalid symbol table")
        strings = sections[link]
        if strings[1] != 3:
            raise ValueError("Missing symbol string table")
        names = _slice(data, strings[4], strings[5])
        for position in range(offset, offset + size, entry_size):
            name, _, _, info, _, defined = struct.unpack("<IIIBBH", _slice(data, position, 16))
            if defined == 0 or info & 0x0f != 2:
                continue
            if name >= len(names) or b"\0" not in names[name:]:
                raise ValueError("Invalid symbol name")
            symbols.add(names[name:names.index(b"\0", name)].decode("ascii"))
    return entry, loads, symbols


def verify(elf: bytes, binary: bytes, config: str, kind: str) -> dict:
    if kind not in {"main", "agent"}:
        raise ValueError("kind must be main or agent")
    entry, loads, symbols = inspect_elf(elf)
    base = min(segment["paddr"] for segment in loads)
    end = max(segment["paddr"] + segment["size"] for segment in loads)
    if base != FLASH_BASE:
        raise ValueError(f"Unexpected flash base 0x{base:08x}; expected 0x{FLASH_BASE:08x}")
    if end - base != len(binary):
        raise ValueError("Binary size does not match ELF load extent")
    if not any(segment["vaddr"] <= (entry & ~1) < segment["vaddr"] + segment["size"]
               and segment["flags"] & 1 for segment in loads):
        raise ValueError("Entry point is outside executable load data")
    expected = bytearray(len(binary))  # objcopy binary's default gap fill is zero.
    for segment in loads:
        image_data = _slice(binary, segment["paddr"] - base, segment["size"])
        load_data = _slice(elf, segment["offset"], segment["size"])
        if image_data != load_data:
            raise ValueError("Binary bytes do not match ELF load data")
        offset = segment["paddr"] - base
        expected[offset:offset + segment["size"]] = load_data
    if expected != binary:
        raise ValueError("Binary gap bytes do not match default zero fill")
    active = set(config.splitlines())
    missing_config = [key for key in REQUIRED_CONFIG if key + "=y" not in active]
    if "CONFIG_TOUCH_IRQ_PIN=31" not in active:
        missing_config.append("CONFIG_TOUCH_IRQ_PIN=31")
    agent_enabled = AGENT_CONFIG + "=y" in active
    if agent_enabled != (kind == "agent"):
        raise ValueError("Independent Agent configuration does not match image kind")
    if missing_config:
        raise ValueError("Missing board config: " + ", ".join(missing_config))
    required_symbols = REQUIRED_SYMBOLS + ((AGENT_SYMBOL,) if kind == "agent" else ())
    missing_symbols = sorted(set(required_symbols) - symbols)
    if missing_symbols:
        raise ValueError("Missing linked functions: " + ", ".join(missing_symbols))
    return {
        "passed": True, "scope": "offline_firmware_delivery", "kind": kind,
        "flash_address": f"0x{base:08x}", "entry_point": f"0x{entry:08x}",
        "binary_bytes": len(binary), "binary_sha256": hashlib.sha256(binary).hexdigest(),
        "elf_sha256": hashlib.sha256(elf).hexdigest(),
        "config_sha256": hashlib.sha256(config.encode()).hexdigest(),
        "matched_file_backed_load_segments": len(loads),
        "binary_matches_load_data_and_zero_filled_gaps": True,
        "touch_irq_pin": 31,
        "required_config_verified": list(REQUIRED_CONFIG),
        "required_linked_functions_verified": list(required_symbols),
        "independent_ai_agent_enabled": agent_enabled,
        "board_tested": False, "firmware_on_board_identified": False,
        "physical_sound_light_radar_touch_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--kind", choices=("main", "agent"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.elf.read_bytes(), args.binary.read_bytes(),
                        args.config.read_bytes().decode("utf-8"), args.kind)
    except (OSError, ValueError, struct.error) as exc:
        report = {"passed": False, "scope": "offline_firmware_delivery", "kind": args.kind,
                  "error": str(exc), "board_tested": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(("PASS" if report["passed"] else "FAIL") + " offline firmware delivery: " + args.kind)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
