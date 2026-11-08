from __future__ import annotations

import unittest
from unittest import mock

from dma2ray import installer


class AssetTests(unittest.TestCase):
    def test_known_architectures(self) -> None:
        cases = {
            "x86_64": "Xray-linux-64.zip",
            "aarch64": "Xray-linux-arm64-v8a.zip",
            "armv7l": "Xray-linux-arm32-v7a.zip",
            "armv6l": "Xray-linux-arm32-v6.zip",
            "i686": "Xray-linux-32.zip",
            "riscv64": "Xray-linux-riscv64.zip",
        }
        for machine, expected in cases.items():
            with self.subTest(machine=machine):
                with mock.patch.object(installer.platform, "machine", return_value=machine):
                    self.assertEqual(installer.asset_name("xray"), expected)

    def test_unknown_architecture(self) -> None:
        with mock.patch.object(installer.platform, "machine", return_value="mips"):
            with self.assertRaises(RuntimeError):
                installer.asset_name("xray")


if __name__ == "__main__":
    unittest.main()
