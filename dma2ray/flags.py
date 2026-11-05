from __future__ import annotations

import re

# Two-letter ISO codes shown only when they appear as an uppercase word
# (e.g. "DE-1", "NL Amsterdam"), to avoid false positives like "in"/"at".
_CODE_FLAGS = {
    "at": "🇦🇹",
    "au": "🇦🇺",
    "be": "🇧🇪",
    "bg": "🇧🇬",
    "br": "🇧🇷",
    "ca": "🇨🇦",
    "ch": "🇨🇭",
    "cz": "🇨🇿",
    "de": "🇩🇪",
    "dk": "🇩🇰",
    "ee": "🇪🇪",
    "es": "🇪🇸",
    "fi": "🇫🇮",
    "fr": "🇫🇷",
    "gb": "🇬🇧",
    "gr": "🇬🇷",
    "hk": "🇭🇰",
    "hu": "🇭🇺",
    "ie": "🇮🇪",
    "il": "🇮🇱",
    "in": "🇮🇳",
    "is": "🇮🇸",
    "it": "🇮🇹",
    "jp": "🇯🇵",
    "kr": "🇰🇷",
    "lt": "🇱🇹",
    "lv": "🇱🇻",
    "md": "🇲🇩",
    "nl": "🇳🇱",
    "no": "🇳🇴",
    "nz": "🇳🇿",
    "pl": "🇵🇱",
    "pt": "🇵🇹",
    "ro": "🇷🇴",
    "rs": "🇷🇸",
    "ru": "🇷🇺",
    "se": "🇸🇪",
    "sg": "🇸🇬",
    "sk": "🇸🇰",
    "tr": "🇹🇷",
    "tw": "🇹🇼",
    "ua": "🇺🇦",
    "us": "🇺🇸",
}

_CITY_FLAGS = {
    "amsterdam": "🇳🇱",
    "andorra": "🇦🇩",
    "athens": "🇬🇷",
    "auckland": "🇳🇿",
    "bangkok": "🇹🇭",
    "barcelona": "🇪🇸",
    "berlin": "🇩🇪",
    "bratislava": "🇸🇰",
    "brussels": "🇧🇪",
    "bucharest": "🇷🇴",
    "budapest": "🇭🇺",
    "chicago": "🇺🇸",
    "copenhagen": "🇩🇰",
    "dallas": "🇺🇸",
    "dubai": "🇦🇪",
    "dublin": "🇮🇪",
    "frankfurt": "🇩🇪",
    "geneva": "🇨🇭",
    "helsinki": "🇫🇮",
    "hong kong": "🇭🇰",
    "istanbul": "🇹🇷",
    "kiev": "🇺🇦",
    "kyiv": "🇺🇦",
    "lisbon": "🇵🇹",
    "london": "🇬🇧",
    "los angeles": "🇺🇸",
    "madrid": "🇪🇸",
    "miami": "🇺🇸",
    "milan": "🇮🇹",
    "montreal": "🇨🇦",
    "moscow": "🇷🇺",
    "new york": "🇺🇸",
    "oslo": "🇳🇴",
    "paris": "🇫🇷",
    "prague": "🇨🇿",
    "riga": "🇱🇻",
    "rome": "🇮🇹",
    "seattle": "🇺🇸",
    "seoul": "🇰🇷",
    "singapore": "🇸🇬",
    "sofia": "🇧🇬",
    "stockholm": "🇸🇪",
    "tokyo": "🇯🇵",
    "toronto": "🇨🇦",
    "vienna": "🇦🇹",
    "vilnius": "🇱🇹",
    "warsaw": "🇵🇱",
    "zurich": "🇨🇭",
}

_TLD_FLAGS = {
    "at": "🇦🇹",
    "au": "🇦🇺",
    "be": "🇧🇪",
    "br": "🇧🇷",
    "ca": "🇨🇦",
    "ch": "🇨🇭",
    "cz": "🇨🇿",
    "de": "🇩🇪",
    "dk": "🇩🇰",
    "es": "🇪🇸",
    "fi": "🇫🇮",
    "fr": "🇫🇷",
    "gr": "🇬🇷",
    "hk": "🇭🇰",
    "hu": "🇭🇺",
    "ie": "🇮🇪",
    "il": "🇮🇱",
    "in": "🇮🇳",
    "is": "🇮🇸",
    "it": "🇮🇹",
    "jp": "🇯🇵",
    "kr": "🇰🇷",
    "nl": "🇳🇱",
    "no": "🇳🇴",
    "nz": "🇳🇿",
    "pl": "🇵🇱",
    "pt": "🇵🇹",
    "ro": "🇷🇴",
    "ru": "🇷🇺",
    "se": "🇸🇪",
    "sg": "🇸🇬",
    "sk": "🇸🇰",
    "tr": "🇹🇷",
    "tw": "🇹🇼",
    "ua": "🇺🇦",
    "uk": "🇬🇧",
    "us": "🇺🇸",
}

_CODE_WORD = re.compile(r"(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])")


def flag_for(name: str, address: str = "") -> str:
    """Best-effort country flag for a profile name/address; "" if unknown."""
    stripped = name.strip()
    if len(stripped) == 2 and stripped.isalpha():
        flag = _CODE_FLAGS.get(stripped.lower())
        if flag:
            return flag
    for match in _CODE_WORD.finditer(stripped):
        flag = _CODE_FLAGS.get(match.group(1).lower())
        if flag:
            return flag
    lowered = stripped.lower()
    for token, flag in sorted(_CITY_FLAGS.items(), key=lambda item: -len(item[0])):
        if token in lowered:
            return flag
    host = address.strip().lower().rstrip(".")
    if "." in host:
        tld = host.rsplit(".", 1)[-1]
        flag = _TLD_FLAGS.get(tld)
        if flag:
            return flag
    return ""
