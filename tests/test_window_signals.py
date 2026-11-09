"""Сигнатуры обработчиков сигналов в window.py.

Сигналы вида notify::* передают (row, pspec): если обработчик объявлен как
def handler(self, row), возникает TypeError и настройка не сохраняется.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

WINDOW = Path(__file__).resolve().parent.parent / "dma2ray" / "window.py"


class WindowSignalSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tree = ast.parse(WINDOW.read_text("utf-8"))
        cls.defs: dict[str, ast.FunctionDef] = {}
        for node in ast.walk(cls.tree):
            if isinstance(node, ast.FunctionDef):
                cls.defs[node.name] = node

    def _direct_notify_connections(self) -> list[tuple[int, str, str]]:
        """Сигналы notify::*, подключённые напрямую к self.метод (не лямбда)."""
        found: list[tuple[int, str, str]] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "connect"):
                continue
            if len(node.args) < 2:
                continue
            signal = node.args[0]
            target = node.args[1]
            if not (isinstance(signal, ast.Constant) and isinstance(signal.value, str)):
                continue
            if not signal.value.startswith("notify::"):
                continue
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                found.append((node.lineno, signal.value, target.attr))
        return found

    def test_notify_handlers_accept_row_and_param(self) -> None:
        connections = self._direct_notify_connections()
        self.assertTrue(connections, "не найдено прямых notify-подключений")
        for lineno, signal, name in connections:
            fn = self.defs.get(name)
            self.assertIsNotNone(fn, f"строка {lineno}: обработчик {name} не найден")
            assert fn is not None
            args = fn.args
            positional = len(args.posonlyargs) + len(args.args)
            has_varargs = args.vararg is not None
            self.assertTrue(
                positional >= 3 or has_varargs,
                f"строка {lineno}: {name} подключён к «{signal}», но принимает "
                f"{positional - 1} позиционных аргументов без *args — "
                f"сигнал передаёт (row, pspec)",
            )

    def test_known_broken_handlers_are_fixed(self) -> None:
        """Регрессия: переключатели «Автозапуск» и «Трей» падали с TypeError."""
        for name in ("_settings_autostart", "_settings_tray"):
            fn = self.defs.get(name)
            self.assertIsNotNone(fn, f"{name} не найден")
            assert fn is not None
            arg_names = [a.arg for a in fn.args.args]
            self.assertGreaterEqual(
                len(arg_names), 3, f"{name} должен принимать (self, row, param)"
            )


if __name__ == "__main__":
    unittest.main()
