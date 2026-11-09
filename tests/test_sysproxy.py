from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dma2ray import sysproxy

SCHEMA = "org.gnome.system.proxy"
GETS = {
    (SCHEMA, "mode"): "'none'",
    (SCHEMA + ".http", "host"): "'192.168.5.5'",
    (SCHEMA + ".http", "port"): "3128",
    (SCHEMA + ".https", "host"): "'192.168.5.5'",
    (SCHEMA + ".https", "port"): "3128",
    (SCHEMA + ".socks", "host"): "''",
    (SCHEMA + ".socks", "port"): "0",
}


class _Runner:
    """Fake subprocess.run recording gsettings calls."""

    def __init__(self, *, fail_get: tuple[str, str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_get = fail_get

    def __call__(self, cmd, **_kwargs):
        self.calls.append(list(cmd))
        if cmd[0] == "gsettings" and cmd[1] == "get":
            key = (cmd[2], cmd[3])
            if self.fail_get == key:
                return SimpleNamespace(returncode=1, stdout="", stderr="no such key")
            return SimpleNamespace(returncode=0, stdout=GETS[key], stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def sets(self) -> list[list[str]]:
        return [call for call in self.calls if call[:2] == ["gsettings", "set"]]


class GnomeSysProxyTests(unittest.TestCase):
    """Все тесты работают с подменённым subprocess и which всё время жизни."""

    def setUp(self) -> None:
        sysproxy.reset_for_tests()
        self.addCleanup(sysproxy.reset_for_tests)
        env_patcher = mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        self.runner = _Runner()
        sub_patcher = mock.patch.object(sysproxy, "subprocess")
        self.sub = sub_patcher.start()
        self.sub.run = self.runner
        self.addCleanup(sub_patcher.stop)
        which_patcher = mock.patch.object(
            sysproxy, "which", return_value="/usr/bin/gsettings"
        )
        which_patcher.start()
        self.addCleanup(which_patcher.stop)

    def test_apply_sets_manual_proxy(self) -> None:
        sysproxy.apply(10809, 10808)
        self.assertTrue(sysproxy.is_applied())
        sets = self.runner.sets()
        self.assertIn(["gsettings", "set", SCHEMA, "mode", "'manual'"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".http", "host", "'127.0.0.1'"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".http", "port", "10809"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".https", "port", "10809"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".socks", "host", "'127.0.0.1'"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".socks", "port", "10808"], sets)

    def test_revert_restores_previous_values(self) -> None:
        sysproxy.apply(10809, 10808)
        self.runner.calls.clear()
        sysproxy.revert()
        self.assertFalse(sysproxy.is_applied())
        sets = self.runner.sets()
        self.assertIn(["gsettings", "set", SCHEMA, "mode", "'none'"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".http", "host", "'192.168.5.5'"], sets)
        self.assertIn(["gsettings", "set", SCHEMA + ".http", "port", "3128"], sets)

    def test_apply_twice_is_noop(self) -> None:
        sysproxy.apply(10809, 10808)
        count = len(self.runner.calls)
        sysproxy.apply(10809, 10808)
        self.assertEqual(len(self.runner.calls), count)

    def test_revert_without_apply_is_safe(self) -> None:
        sysproxy.revert()
        self.assertFalse(sysproxy.is_applied())

    def test_get_failure_raises_and_not_applied(self) -> None:
        self.runner.fail_get = (SCHEMA + ".socks", "port")
        with self.assertRaises(sysproxy.SysProxyError):
            sysproxy.apply(10809, 10808)
        self.assertFalse(sysproxy.is_applied())

    def test_missing_gsettings_binary(self) -> None:
        with mock.patch.object(sysproxy, "which", return_value=None):
            with self.assertRaises(sysproxy.SysProxyError):
                sysproxy.apply(10809, 10808)
        self.assertFalse(sysproxy.is_applied())

    def test_cinnamon_and_mate_schemas(self) -> None:
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "X-Cinnamon"}):
            self.assertEqual(
                sysproxy._gsettings_schema(sysproxy._desktop()),
                "org.cinnamon.system.proxy",
            )
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "MATE"}):
            self.assertEqual(
                sysproxy._gsettings_schema(sysproxy._desktop()), "org.mate.proxy"
            )

    def test_sub_schema_split(self) -> None:
        self.assertEqual(
            sysproxy._sub_schema(SCHEMA, "http.host"),
            (SCHEMA + ".http", "host"),
        )
        self.assertEqual(sysproxy._sub_schema(SCHEMA, "mode"), (SCHEMA, "mode"))


class _IniRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kwargs):
        self.calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class KdeSysProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        sysproxy.reset_for_tests()
        self.addCleanup(sysproxy.reset_for_tests)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env_patcher = mock.patch.dict(
            os.environ,
            {"XDG_CURRENT_DESKTOP": "KDE", "XDG_CONFIG_HOME": self.tmp.name},
        )
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        self.config = Path(self.tmp.name) / "kioslaverc"
        self.runner = _IniRunner()
        sub_patcher = mock.patch.object(sysproxy, "subprocess")
        self.sub = sub_patcher.start()
        self.sub.run = self.runner
        self.addCleanup(sub_patcher.stop)
        which_patcher = mock.patch.object(sysproxy, "which", return_value=None)
        which_patcher.start()
        self.addCleanup(which_patcher.stop)

    def test_manual_ini_write_and_restore(self) -> None:
        original = "[Proxy Settings]\nProxyType=0\nhttpProxy=\n"
        self.config.write_text(original, "utf-8")

        sysproxy.apply(10809, 10808)

        text = self.config.read_text("utf-8")
        self.assertIn("ProxyType=1", text)
        self.assertIn("httpProxy=http://127.0.0.1 10809", text)
        self.assertIn("socksProxy=socks://127.0.0.1 10808", text)
        self.assertEqual(text.count("ProxyType="), 1)
        self.assertTrue(sysproxy.is_applied())

        sysproxy.revert()
        self.assertEqual(self.config.read_text("utf-8"), original)
        self.assertFalse(sysproxy.is_applied())

    def test_fresh_config_created_and_removed_on_revert(self) -> None:
        sysproxy.apply(10809, 10808)
        self.assertTrue(self.config.is_file())
        sysproxy.revert()
        self.assertFalse(self.config.exists())

    def test_kwriteconfig_used_when_available(self) -> None:
        def fake_which(name: str):
            if name.startswith(("kwriteconfig", "dbus-send")):
                return f"/usr/bin/{name}"
            return None

        with mock.patch.object(sysproxy, "which", side_effect=fake_which):
            sysproxy.apply(10809, 10808)

        commands = [" ".join(call) for call in self.runner.calls]
        self.assertTrue(any("kwriteconfig" in cmd and "ProxyType" in cmd for cmd in commands))
        self.assertTrue(any("httpProxy" in cmd for cmd in commands))
        sysproxy.revert()


if __name__ == "__main__":
    unittest.main()
