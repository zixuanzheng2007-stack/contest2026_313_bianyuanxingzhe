# SPDX-License-Identifier: Apache-2.0
"""Delivery checks must reject image/ELF drift, wrong addresses and incomplete builds."""
import struct
import unittest

from verify_firmware_candidate import (AGENT_CONFIG, AGENT_SYMBOL, FLASH_BASE,
                                       REQUIRED_CONFIG, REQUIRED_SYMBOLS, verify)


def fixture(kind="main", base=FLASH_BASE, omit=None):
    image = bytes(range(64))
    data = bytearray(2048)
    names = b"\0"
    table = bytearray(16)
    for symbol in REQUIRED_SYMBOLS + ((AGENT_SYMBOL,) if kind == "agent" else ()):
        if symbol != omit:
            table.extend(struct.pack("<IIIBBH", len(names), base + 1, 4, 0x12, 0, 1))
            names += symbol.encode() + b"\0"
    data[:52] = struct.pack("<16sHHIIIIIHHHHHH", b"\x7fELF\x01\x01\x01" + b"\0" * 9,
                            2, 40, 1, base + 1, 52, 1024, 0, 52, 32, 3, 40, 3, 0)
    # Include a RAM initializer and BSS to exercise physical versus virtual addresses.
    for index, segment in enumerate(((1, 256, base, base, 48, 48, 5, 4),
                                      (1, 304, 0x20000000, base + 48, 16, 16, 6, 4),
                                      (1, 0, 0x20000010, base + 64, 0, 4096, 6, 4))):
        data[52 + index * 32:84 + index * 32] = struct.pack("<IIIIIIII", *segment)
    data[256:320] = image
    data[512:512 + len(table)] = table
    data[768:768 + len(names)] = names
    data[1064:1104] = struct.pack("<IIIIIIIIII", 0, 2, 0, 0, 512, len(table), 2, 0, 4, 16)
    data[1104:1144] = struct.pack("<IIIIIIIIII", 0, 3, 0, 0, 768, len(names), 0, 0, 1, 0)
    config = "\n".join(key + "=y" for key in REQUIRED_CONFIG)
    config += "\nCONFIG_TOUCH_IRQ_PIN=31\n" + (AGENT_CONFIG + "=y" if kind == "agent" else "# " + AGENT_CONFIG + " is not set") + "\n"
    return bytes(data), image, config


class FirmwareCandidateTests(unittest.TestCase):
    def test_main_and_agent_validate_physical_loads_without_claiming_board_test(self):
        for kind in ("main", "agent"):
            with self.subTest(kind=kind):
                report = verify(*fixture(kind), kind)
                self.assertTrue(report["passed"])
                self.assertEqual(report["flash_address"], "0x12010000")
                self.assertEqual(report["matched_file_backed_load_segments"], 2)
                self.assertEqual(report["independent_ai_agent_enabled"], kind == "agent")
                self.assertFalse(report["board_tested"])

    def test_corrupted_or_extra_binary_bytes_rejected(self):
        elf, image, config = fixture()
        for bad in (b"!" + image[1:], image[:-1], image + b"!"):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                verify(elf, bad, config, "main")

    def test_old_flashing_example_address_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "flash base"):
            verify(*fixture(base=0x12020000), "main")

    def test_missing_board_config_or_linked_snapshot_rejected(self):
        elf, image, config = fixture()
        with self.assertRaisesRegex(ValueError, "board config"):
            verify(elf, image, config.replace("CONFIG_BSP_UART3_RX_USING_DMA=y", ""), "main")
        with self.assertRaisesRegex(ValueError, "linked functions"):
            verify(*fixture(omit="ew_snapshot_format"), "main")
        with self.assertRaisesRegex(ValueError, "TOUCH_IRQ_PIN"):
            verify(elf, image, config.replace("CONFIG_TOUCH_IRQ_PIN=31", "CONFIG_TOUCH_IRQ_PIN=41"), "main")

    def test_gap_corruption_does_not_pass_full_binary_comparison(self):
        elf, image, config = fixture()
        elf = bytearray(elf)
        # Shift the RAM initializer's physical load by four bytes.
        struct.pack_into("<I", elf, 84 + 12, FLASH_BASE + 52)
        good = image[:48] + b"\0" * 4 + image[48:]
        self.assertTrue(verify(bytes(elf), good, config, "main")["passed"])
        with self.assertRaisesRegex(ValueError, "gap bytes"):
            verify(bytes(elf), image[:48] + b"bad!" + image[48:], config, "main")

    def test_main_does_not_qualify_as_independent_agent(self):
        with self.assertRaisesRegex(ValueError, "Agent configuration"):
            verify(*fixture(), "agent")
        with self.assertRaisesRegex(ValueError, "linked functions"):
            verify(*fixture("agent", omit=AGENT_SYMBOL), "agent")

    def test_truncated_or_wrong_architecture_elf_rejected(self):
        elf, image, config = fixture()
        for bad in (elf[:30], elf[:18] + b"\x03\x00" + elf[20:], elf[:1100]):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                verify(bad, image, config, "main")


if __name__ == "__main__":
    unittest.main(verbosity=2)
