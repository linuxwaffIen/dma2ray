from __future__ import annotations

import unittest
from unittest import mock

from dma2ray import installer

TAG = "v1.19.34"


class AssetTests(unittest.TestCase):
    def test_supported_architectures(self) -> None:
        cases = {
            "x86_64": f"mihomo-linux-amd64-v1-{TAG}.gz",
            "amd64": f"mihomo-linux-amd64-v1-{TAG}.gz",
            "aarch64": f"mihomo-linux-arm64-{TAG}.gz",
            "arm64": f"mihomo-linux-arm64-{TAG}.gz",
            "armv7l": f"mihomo-linux-armv7-{TAG}.gz",
            "armv7": f"mihomo-linux-armv7-{TAG}.gz",
        }
        for machine, expected in cases.items():
            with self.subTest(machine=machine):
                self.assertEqual(installer.asset_name(machine, TAG), expected)
                self.assertIn(machine, installer.SUPPORTED_ARCHS)

    def test_amd64_uses_compatible_v1_build(self) -> None:
        self.assertEqual(installer.MIHOMO_TAGS["x86_64"], "amd64-v1")

    def test_unsupported_architectures_are_not_listed(self) -> None:
        for machine in ("i686", "riscv64", "armv6l", "mips"):
            self.assertNotIn(machine, installer.SUPPORTED_ARCHS)
            with self.assertRaises(RuntimeError):
                installer.asset_name(machine, TAG)

    def test_latest_tag(self) -> None:
        class FakeResponse:
            def __init__(self, data: bytes) -> None:
                self.data = data

            def read(self) -> bytes:
                return self.data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        fake = FakeResponse(b"v1.20.0\n")
        with mock.patch.object(installer.urllib.request, "urlopen", return_value=fake):
            self.assertEqual(installer.latest_tag(), "v1.20.0")


if __name__ == "__main__":
    unittest.main()
