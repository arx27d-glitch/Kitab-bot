"""Video quality detection from file names (1080p / 720p / 480p ...)."""
import re
from collections import OrderedDict
from typing import Iterable, Optional

# highest first (button order)
ORDER = ["2160p", "1440p", "1080p", "720p", "576p", "480p", "360p", "240p"]

_RES = r"(2160|1440|1080|720|576|480|360|240)"
_P = re.compile(rf"(?<!\d){_RES}p", re.I)               # 1080p  720P  480p
_X = re.compile(rf"\d{{3,4}}\s?x\s?{_RES}(?!\d)", re.I)  # 1920x1080
_K = re.compile(r"(?<![a-z0-9])(4k|uhd)(?![a-z0-9])", re.I)


def detect_quality(text: str) -> Optional[str]:
    """Returns e.g. '1080p' if the text (file name) mentions a quality, else None."""
    text = text or ""
    m = _P.search(text) or _X.search(text)
    if m:
        return f"{m.group(1)}p"
    if _K.search(text):
        return "2160p"
    return None


def quality_counts(titles: Iterable[str]) -> "OrderedDict[str, int]":
    """{'1080p': 3, '720p': 2, ...} ordered high -> low."""
    found = {}
    for t in titles:
        q = detect_quality(t)
        if q:
            found[q] = found.get(q, 0) + 1
    return OrderedDict(sorted(found.items(), key=lambda kv: ORDER.index(kv[0])))
