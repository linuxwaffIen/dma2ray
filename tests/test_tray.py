from __future__ import annotations

import json
import socket
import threading
import unittest

from dma2ray.tray import TrayController


class TrayProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.received: list[str] = []
        self.controller = TrayController(
            on_show=lambda: self.received.append("show"),
            on_toggle=lambda: self.received.append("toggle"),
            on_quit=lambda: self.received.append("quit"),
        )

    def test_commands_are_dispatched(self) -> None:
        server, client = socket.socketpair()
        thread = threading.Thread(target=self.controller._read_loop, args=(server,))
        thread.start()
        try:
            # "quit" — последняя команда: после неё read_loop закрывает сокет.
            for command in ("show", "toggle", "bogus", "not json", "quit"):
                try:
                    client.sendall((json.dumps({"cmd": command}) + "\n").encode("utf-8"))
                except OSError:
                    break
            try:
                client.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        finally:
            client.close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.received, ["show", "toggle", "quit"])

    def test_invalid_utf8_is_ignored(self) -> None:
        server, client = socket.socketpair()
        thread = threading.Thread(target=self.controller._read_loop, args=(server,))
        thread.start()
        try:
            client.sendall(b"\xff\xfe\n")
            client.sendall(b'{"cmd": "show"}\n')
            client.shutdown(socket.SHUT_WR)
        finally:
            client.close()
            thread.join(timeout=2)
        self.assertEqual(self.received, ["show"])


if __name__ == "__main__":
    unittest.main()
