from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dma2ray.state import DEFAULT_SETTINGS, Store

UUID = "11111111-2222-3333-4444-555555555555"
URI_1 = f"vless://{UUID}@example.com:443?type=ws#first"
URI_2 = f"vless://{UUID}@example.net:443?type=grpc#second"


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config" / "state.json"
        self.store = Store(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_profile_deduplicates_by_uri(self) -> None:
        first = self.store.add_profile("First", URI_1)
        again = self.store.add_profile("Renamed", URI_1)
        self.assertEqual(first.id, again.id)
        self.assertEqual(len(self.store.profiles), 1)
        self.assertEqual(again.name, "Renamed")
        self.assertEqual(self.store.settings["selected_profile_id"], first.id)

    def test_select_and_remove_profile(self) -> None:
        first = self.store.add_profile("First", URI_1)
        second = self.store.add_profile("Second", URI_2)
        self.store.select_profile(second.id)
        self.assertEqual(self.store.selected_profile.id, second.id)
        self.store.remove_profile(second.id)
        self.assertEqual(self.store.selected_profile.id, first.id)

    def test_removing_unknown_profile_is_safe(self) -> None:
        self.store.add_profile("First", URI_1)
        self.store.remove_profile("missing")
        self.assertEqual(len(self.store.profiles), 1)

    def test_rename_profile(self) -> None:
        profile = self.store.add_profile("First", URI_1)
        self.store.rename_profile(profile.id, "  New name  ")
        self.assertEqual(self.store.get_profile(profile.id).name, "New name")
        self.store.rename_profile(profile.id, "   ")
        self.assertEqual(self.store.get_profile(profile.id).name, "New name")

    def test_subscription_replaces_its_profiles(self) -> None:
        sub = self.store.add_subscription("Sub", "https://example.com/sub")
        self.store.add_profile("Manual", URI_2)
        self.store.replace_subscription_profiles(
            sub.id, [("A", URI_1), ("B", URI_2), ("A duplicate", URI_1)]
        )
        self.assertEqual(len(self.store.profiles_for_subscription(sub.id)), 2)
        self.assertEqual(self.store.get_subscription(sub.id).last_error, None)
        self.assertGreater(self.store.get_subscription(sub.id).updated_at, 0)

    def test_subscription_update_keeps_selected_profile(self) -> None:
        sub = self.store.add_subscription("Sub", "https://example.com/sub")
        self.store.replace_subscription_profiles(sub.id, [("A", URI_1)])
        selected = self.store.selected_profile
        self.assertIsNotNone(selected)
        self.store.replace_subscription_profiles(sub.id, [("A new", URI_1)])
        self.assertEqual(self.store.selected_profile.uri, URI_1)

    def test_remove_subscription_removes_profiles(self) -> None:
        sub = self.store.add_subscription("Sub", "https://example.com/sub")
        self.store.replace_subscription_profiles(sub.id, [("A", URI_1)])
        manual = self.store.add_profile("Manual", URI_2)
        self.store.remove_subscription(sub.id)
        self.assertEqual(len(self.store.subscriptions), 0)
        self.assertEqual([profile.id for profile in self.store.profiles], [manual.id])

    def test_state_persists(self) -> None:
        sub = self.store.add_subscription("Sub", "https://example.com/sub")
        self.store.replace_subscription_profiles(sub.id, [("A", URI_1)])
        self.store.set_setting("socks_port", 12345)
        self.store.select_profile(self.store.profiles[0].id)

        reopened = Store(self.path)
        self.assertEqual(len(reopened.profiles), 1)
        self.assertEqual(reopened.profiles[0].uri, URI_1)
        self.assertEqual(len(reopened.subscriptions), 1)
        self.assertEqual(reopened.settings["socks_port"], 12345)
        self.assertEqual(
            reopened.settings["selected_profile_id"], reopened.profiles[0].id
        )

    def test_corrupt_state_falls_back_to_defaults(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not json", "utf-8")
        store = Store(self.path)
        self.assertEqual(store.profiles, [])
        for key, value in DEFAULT_SETTINGS.items():
            self.assertEqual(store.settings[key], value)

    def test_invalid_settings_are_repaired(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "profiles": [{"id": "p1", "name": "P", "uri": URI_1}],
                    "subscriptions": [],
                    "settings": {
                        "selected_profile_id": "missing",
                        "socks_port": "not a number",
                        "tun_enabled": "yes",
                        "log_level": "verbose",
                    },
                }
            ),
            "utf-8",
        )
        store = Store(self.path)
        self.assertEqual(store.settings["selected_profile_id"], "p1")
        self.assertEqual(store.settings["socks_port"], DEFAULT_SETTINGS["socks_port"])
        self.assertEqual(store.settings["tun_enabled"], DEFAULT_SETTINGS["tun_enabled"])
        self.assertEqual(store.settings["log_level"], "warning")

    def test_old_state_gets_new_settings_defaults(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "profiles": [],
                    "subscriptions": [],
                    "settings": {"tun_enabled": False},
                }
            ),
            "utf-8",
        )
        store = Store(self.path)
        self.assertTrue(store.settings["auto_ping"])
        self.assertFalse(store.settings["sort_by_latency"])

    def test_mode_migrates_from_tun_enabled(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"profiles": [], "subscriptions": [], "settings": {"tun_enabled": False}}),
            "utf-8",
        )
        self.assertEqual(Store(self.path).mode, "proxy")
        self.path.write_text(
            json.dumps({"profiles": [], "subscriptions": [], "settings": {"tun_enabled": True}}),
            "utf-8",
        )
        self.assertEqual(Store(self.path).mode, "vpn")

    def test_invalid_mode_is_repaired(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "profiles": [],
                    "subscriptions": [],
                    "settings": {"mode": "turbo", "tun_enabled": False},
                }
            ),
            "utf-8",
        )
        store = Store(self.path)
        self.assertEqual(store.mode, "proxy")

    def test_set_mode_mirrors_tun_enabled_and_persists(self) -> None:
        self.store.set_mode("system")
        self.assertEqual(self.store.mode, "system")
        self.assertFalse(self.store.settings["tun_enabled"])
        self.store.set_mode("vpn")
        self.assertTrue(self.store.settings["tun_enabled"])
        reopened = Store(self.path)
        self.assertEqual(reopened.mode, "vpn")
        with self.assertRaises(ValueError):
            self.store.set_mode("turbo")

    def test_saved_state_has_restricted_permissions(self) -> None:
        self.store.add_profile("First", URI_1)
        mode = self.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
