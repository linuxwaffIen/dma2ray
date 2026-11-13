from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from dma2ray.config import build_config, dump_yaml
from dma2ray.vless import parse_vless

ROOT = Path(__file__).resolve().parent.parent
UUID = "11111111-2222-3333-4444-555555555555"


def _find_mihomo() -> str | None:
    # Скачанное приложением ядро, затем системный mihomo в PATH.
    from dma2ray import paths

    if paths.CORE_PATH.is_file():
        return str(paths.CORE_PATH)
    return shutil.which("mihomo")


class MihomoConfigValidationTests(unittest.TestCase):
    """Validate generated configs with a real mihomo binary, if available."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mihomo = _find_mihomo()
        if not cls.mihomo:
            raise unittest.SkipTest("mihomo binary not found")

    def _validate(self, uri: str, *, tun: bool) -> None:
        profile = parse_vless(uri)
        config = build_config(
            profile,
            tun=tun,
            socks_port=10808,
            http_port=10809,
            log_level="warning",
            address_override="127.0.0.1",
        )
        with tempfile.TemporaryDirectory() as workdir:
            path = Path(workdir) / "config.yaml"
            path.write_text(dump_yaml(config), encoding="utf-8")
            try:
                result = subprocess.run(
                    [self.mihomo, "-t", "-d", workdir, "-f", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except FileNotFoundError:
                raise unittest.SkipTest("mihomo binary not runnable")
            detail = (result.stdout + "\n" + result.stderr).strip()
            self.assertEqual(result.returncode, 0, detail)

    def test_common_transports_in_socks_mode(self) -> None:
        links = [
            f"vless://{UUID}@127.0.0.1:443?encryption=none&security=none&type=tcp#tcp",
            f"vless://{UUID}@127.0.0.1:443?encryption=none&security=tls&type=ws&path=%2Fws#ws",
            f"vless://{UUID}@127.0.0.1:443?encryption=none&security=tls&type=grpc&serviceName=svc#grpc",
            f"vless://{UUID}@127.0.0.1:443?encryption=none&security=tls&type=httpupgrade&path=%2Fup#up",
        ]
        for link in links:
            with self.subTest(link=link):
                self._validate(link, tun=False)

    def test_reality_and_tun_mode(self) -> None:
        link = (
            f"vless://{UUID}@127.0.0.1:443?encryption=none&security=reality"
            "&type=tcp&flow=xtls-rprx-vision&sni=example.com"
            "&fp=chrome&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA#reality"
        )
        self._validate(link, tun=False)
        self._validate(link, tun=True)

    def test_plain_and_ipv6_in_tun_mode(self) -> None:
        links = [
            f"vless://{UUID}@127.0.0.1:443?encryption=none&security=none&type=tcp#plain",
            f"vless://{UUID}@[::1]:443?encryption=none&security=none&type=tcp#ipv6",
        ]
        for link in links:
            with self.subTest(link=link):
                self._validate(link, tun=True)


if __name__ == "__main__":
    unittest.main()
