from __future__ import annotations

import base64
from typing import Any

from .state import Store


class ImportError_(Exception):
    pass


def parse_import_list(text: str) -> list[str]:
    uris: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("vless://"):
            if line not in seen:
                seen.add(line)
                uris.append(line)
            continue
        # Try to decode base64/plain text in case someone pastes a whole block
        try:
            compact = "".join(line.split())
            padded = compact + "=" * (-len(compact) % 4)
            decoded = base64.b64decode(padded, altchars=b"-_").decode("utf-8")
            for subline in decoded.splitlines():
                subline = subline.strip()
                if subline.lower().startswith("vless://") and subline not in seen:
                    seen.add(subline)
                    uris.append(subline)
        except Exception:
            continue
    return uris


def import_uris(store: Store, uris: list[str]) -> int:
    added = 0
    for uri in uris:
        profile = store.add_profile(uri.split("@")[-1][:80], uri)
        if profile:
            added += 1
    return added
