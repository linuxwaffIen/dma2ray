from __future__ import annotations

import unittest

from dma2ray.flags import flag_for


class FlagDetectionTests(unittest.TestCase):
    def test_two_letter_name(self) -> None:
        self.assertEqual(flag_for("US"), "🇺🇸")
        self.assertEqual(flag_for("de"), "🇩🇪")

    def test_uppercase_code_word(self) -> None:
        self.assertEqual(flag_for("DE-1"), "🇩🇪")
        self.assertEqual(flag_for("NL Amsterdam"), "🇳🇱")
        self.assertEqual(flag_for("Tokyo JP"), "🇯🇵")

    def test_lowercase_words_are_ignored(self) -> None:
        # "in"/"at" как обычные слова не должны давать флаги
        self.assertEqual(flag_for("Прокси in"), "")

    def test_city_names(self) -> None:
        self.assertEqual(flag_for("Frankfurt am Main"), "🇩🇪")
        self.assertEqual(flag_for("server-vpn Singapore"), "🇸🇬")
        self.assertEqual(flag_for("Москва"), "")

    def test_tld_fallback(self) -> None:
        self.assertEqual(flag_for("node", "example.de"), "🇩🇪")
        self.assertEqual(flag_for("node", "example.com"), "")
        self.assertEqual(flag_for("node", ""), "")

    def test_unknown_is_empty(self) -> None:
        self.assertEqual(flag_for(""), "")
        self.assertEqual(flag_for("мой прокси"), "")


if __name__ == "__main__":
    unittest.main()
