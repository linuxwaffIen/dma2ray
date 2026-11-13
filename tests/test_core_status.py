from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from dma2ray.core import CoreManager, CoreStatus, find_core, preferred_kernel_type

URI = "vless://11111111-2222-3333-4444-555555555555@example.com:443?type=ws#test"


def _wait_for(predicate, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class CoreStatusTests(unittest.TestCase):
    """A failed start must report "error", not "stopped"."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from dma2ray.state import Store

        self.store = Store(Path(self.tmp.name) / "state.json")
        self.statuses: list[CoreStatus] = []

    def _manager(self) -> CoreManager:
        return CoreManager(self.store, self.statuses.append)

    def test_non_executable_core_reports_error(self) -> None:
        fake = Path(self.tmp.name) / "xray"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o600)
        self.store.set_setting("core_path", str(fake))
        manager = self._manager()
        profile = self.store.add_profile("Test", URI)

        manager.start(profile, tun=False)
        self.assertTrue(_wait_for(lambda: manager.status.state == "error"))
        self.assertIn("не исполняемый", manager.status.error or "")
        states = [status.state for status in self.statuses]
        self.assertIn("starting", states)
        self.assertNotIn("stopped", states)

    def test_missing_core_reports_error(self) -> None:
        self.store.set_setting("core_path", str(Path(self.tmp.name) / "no-such-xray"))
        manager = self._manager()
        profile = self.store.add_profile("Test", URI)

        with mock.patch("dma2ray.core.shutil.which", return_value=None):
            manager.start(profile, tun=False)
            self.assertTrue(_wait_for(lambda: manager.status.state == "error"))
        self.assertIn("не найден", manager.status.error or "")

    def test_downloaded_core_is_used_when_nothing_else(self) -> None:
        downloaded = Path(self.tmp.name) / "downloaded-xray"
        downloaded.write_text("#!/bin/sh\n")
        downloaded.chmod(0o755)
        self.store.set_setting("core_path", "")
        with mock.patch("dma2ray.paths.core_path", return_value=downloaded), \
                mock.patch("dma2ray.core.shutil.which", return_value=None):
            self.assertEqual(find_core(self.store), downloaded)

    def test_stop_after_failed_start_reports_stopped(self) -> None:
        fake = Path(self.tmp.name) / "xray"
        fake.write_text("x")
        fake.chmod(0o600)
        self.store.set_setting("core_path", str(fake))
        manager = self._manager()
        profile = self.store.add_profile("Test", URI)

        manager.start(profile, tun=False)
        self.assertTrue(_wait_for(lambda: manager.status.state == "error"))
        manager.stop()
        self.assertTrue(_wait_for(lambda: manager.status.state == "stopped"))

    def test_shutdown_reports_stopped(self) -> None:
        manager = self._manager()
        manager.shutdown()
        self.assertEqual(manager.status.state, "stopped")

    def test_preferred_kernel_type_is_always_mihomo(self) -> None:
        from types import SimpleNamespace

        self.store.set_setting("kernel_mode", "auto")
        self.assertEqual(
            preferred_kernel_type(self.store, SimpleNamespace(protocol="vless")), "mihomo"
        )
        # Даже для протоколов, раньше требовавших Amnezia Xray, ядро одно — mihomo.
        self.assertEqual(
            preferred_kernel_type(self.store, SimpleNamespace(protocol="wireguard")),
            "mihomo",
        )
        self.store.set_setting("kernel_mode", "mihomo")
        self.assertEqual(
            preferred_kernel_type(self.store, SimpleNamespace(protocol="vless")),
            "mihomo",
        )


if __name__ == "__main__":
    unittest.main()
