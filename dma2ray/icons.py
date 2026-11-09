"""Embedded icons for Dma2ray."""

from __future__ import annotations

APP_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3584e4"/>
      <stop offset="1" stop-color="#1a5fb4"/>
    </linearGradient>
    <linearGradient id="shield" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#dbe9ff"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#bg)"/>
  <path d="M64 18 102 32v30c0 24-16 41-38 50-22-9-38-26-38-50V32z" fill="url(#shield)" opacity="0.96"/>
  <path d="M64 30 90 39v23c0 17-11 29-26 36-15-7-26-19-26-36V39z" fill="#1c71d8" opacity="0.16"/>
  <path d="M45 61l12 12 26-27" fill="none" stroke="#1c71d8" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

_TRAY_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <path d="M32 4 56 13v17c0 15-10 25-24 30C18 55 8 45 8 30V13z" fill="{bg}"/>
  <path d="M32 10 50 17v13c0 11-7 19-18 23-11-4-18-12-18-23V17z" fill="{fg}"/>
  {mark}
</svg>
"""

TRAY_ICONS: dict[str, str] = {
    "stopped": _TRAY_TEMPLATE.format(
        bg="#77767b",
        fg="#f6f5f4",
        mark='<path d="M22 32h20" fill="none" stroke="#5e5c64" stroke-width="5" stroke-linecap="round"/>',
    ),
    "starting": _TRAY_TEMPLATE.format(
        bg="#62a0ea",
        fg="#ffffff",
        mark=(
            '<circle cx="23" cy="32" r="3.5" fill="#1c5aa8"/>'
            '<circle cx="32" cy="32" r="3.5" fill="#1c5aa8"/>'
            '<circle cx="41" cy="32" r="3.5" fill="#1c5aa8"/>'
        ),
    ),
    "running": _TRAY_TEMPLATE.format(
        bg="#26a269",
        fg="#ffffff",
        mark='<path d="M21 32l7 7 15-16" fill="none" stroke="#1b6e46" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>',
    ),
}

VPN_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M8 1L2 3.5V8c0 3.7 2.6 6.4 6 7 3.4-.6 6-3.3 6-7V3.5L8 1zm0 2.2l4 1.7v3.1c0 2.6-1.7 4.6-4 5.2-2.3-.6-4-2.6-4-5.2V4.9l4-1.7z" fill="currentColor"/>
</svg>
"""

SPEED_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M5 2L1 6h3v5h2V6h3L5 2zm6 3v5H8l4 4 4-4h-3V5h-2z" fill="currentColor"/>
</svg>
"""

SIGNAL_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <rect x="1" y="11" width="2" height="4" rx="0.5" fill="currentColor"/>
  <rect x="5" y="8" width="2" height="7" rx="0.5" fill="currentColor"/>
  <rect x="9" y="5" width="2" height="10" rx="0.5" fill="currentColor"/>
  <rect x="13" y="2" width="2" height="13" rx="0.5" fill="currentColor"/>
</svg>
"""

STOP_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor"/>
</svg>
"""

SYSTEM_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M7 1v1.1a5 5 0 0 0-1.9.8l-.8-.8-1.4 1.4.8.8A5 5 0 0 0 2.9 6.2H1.8v2h1.1a5 5 0 0 0 .8 1.9l-.8.8 1.4 1.4.8-.8a5 5 0 0 0 1.9.8v1.1h2v-1.1a5 5 0 0 0 1.9-.8l.8.8 1.4-1.4-.8-.8a5 5 0 0 0 .8-1.9h1.1v-2h-1.1a5 5 0 0 0-.8-1.9l.8-.8-1.4-1.4-.8.8A5 5 0 0 0 9 2.1V1H7zm1 4.2a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6z" fill="currentColor"/>
</svg>
"""

SECURITY_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M8 1L2 3.5v5c0 3.7 2.6 6.4 6 7 3.4-.6 6-3.3 6-7v-5L8 1zm0 2.2l4 1.7v3.6c0 2.6-1.7 4.6-4 5.2-2.3-.6-4-2.6-4-5.2V4.9l4-1.7z" fill="currentColor"/>
</svg>
"""

EDIT_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M12.3.8c-.6 0-1.2.2-1.7.7l-9 9c-.4.4-.6.9-.6 1.4v3h3c.5 0 1-.2 1.4-.6l9-9c.9-.9.9-2.5 0-3.4-.6-.7-1.4-1.1-2.1-1.1zm-1.8 3.6l1.1 1.1-7.1 7.1-1.1-1.1 7.1-7.1z" fill="currentColor"/>
</svg>
"""

APPLY_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M13.7 4.7a1 1 0 0 0-1.4-1.4L6 9.6 3.7 7.3a1 1 0 0 0-1.4 1.4l3 3c.4.4 1 .4 1.4 0l7-7z" fill="currentColor"/>
</svg>
"""

WIRELESS_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M8 2.5a11 11 0 0 1 7.8 3.2l-1.4 1.4A9 9 0 0 0 8 4.5a9 9 0 0 0-6.4 2.6L.2 5.7A11 11 0 0 1 8 2.5zm0 4a7 7 0 0 1 4.9 2l-1.4 1.5A5 5 0 0 0 8 8.5a5 5 0 0 0-3.5 1.5L3.1 8.5a7 7 0 0 1 4.9-2zm0 4a3 3 0 0 1 2.1.9L8 13.5l-2.1-2.1A3 3 0 0 1 8 10.5z" fill="currentColor"/>
</svg>
"""

WIRED_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M4 2a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3v2H5v1h6v-1H9v-2h3a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H4zm0 2h8v6H4V4z" fill="currentColor"/>
</svg>
"""

ICONS: dict[str, str] = {
    "io.github.dma2ray.Dma2ray": APP_ICON_SVG,
    "dma2ray-tray-stopped": TRAY_ICONS["stopped"],
    "dma2ray-tray-starting": TRAY_ICONS["starting"],
    "dma2ray-tray-running": TRAY_ICONS["running"],
    "network-vpn-symbolic": VPN_ICON_SVG,
    "network-transmit-receive-symbolic": SPEED_ICON_SVG,
    "network-receive-symbolic": SPEED_ICON_SVG,
    "network-cellular-signal-excellent-symbolic": SIGNAL_ICON_SVG,
    "network-wireless-signal-excellent-symbolic": WIRELESS_ICON_SVG,
    "network-wired-symbolic": WIRED_ICON_SVG,
    "media-playback-stop-symbolic": STOP_ICON_SVG,
    "applications-system-symbolic": SYSTEM_ICON_SVG,
    "security-high-symbolic": SECURITY_ICON_SVG,
    "document-edit-symbolic": EDIT_ICON_SVG,
    "adw-entry-apply-symbolic": APPLY_ICON_SVG,
}
