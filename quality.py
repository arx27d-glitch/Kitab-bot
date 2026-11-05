"""Detects quality (1080p / 720p ...), language (Hindi / Tamil ...) and season (S01 ...) from file names."""
import re
from collections import OrderedDict
from typing import Iterable, List, Optional

# ----------------------------------------------------------------------------
# QUALITY
# ----------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------
# LANGUAGE
# ----------------------------------------------------------------------------
# code -> button name (this order is also the button order)
LANG_NAMES = OrderedDict(
    [
        ("hi", "Hindi"),
        ("en", "English"),
        ("ta", "Tamil"),
        ("te", "Telugu"),
        ("ml", "Malayalam"),
        ("kn", "Kannada"),
        ("bn", "Bengali"),
        ("mr", "Marathi"),
        ("gu", "Gujarati"),
        ("pa", "Punjabi"),
        ("bh", "Bhojpuri"),
        ("ur", "Urdu"),
        ("od", "Odia"),
    ]
)
LANG_ORDER = list(LANG_NAMES)

# whole words only (a word is split on spaces . _ - + [ ] etc). Very short words that are
# also common names / words (ben, mar, kan, pun) are left out on purpose.
_LANG_WORDS = {
    "hi": {"hindi", "hin", "hind"},
    "en": {"english", "eng", "engl"},
    "ta": {"tamil", "tam"},
    "te": {"telugu", "tel"},
    "ml": {"malayalam", "mal", "mlm"},
    "kn": {"kannada", "kannad"},
    "bn": {"bengali", "bangla"},
    "mr": {"marathi"},
    "gu": {"gujarati"},
    "pa": {"punjabi", "panjabi"},
    "bh": {"bhojpuri"},
    "ur": {"urdu"},
    "od": {"odia", "oriya"},
}
_WORD_TO_LANG = {w: code for code, words in _LANG_WORDS.items() for w in words}
_DUAL = re.compile(r"dual[\s._\-]*audio", re.I)


def detect_languages(text: str) -> List[str]:
    """['hi', 'en'] - language codes found in the text, in LANG_ORDER."""
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    found = {_WORD_TO_LANG[t] for t in tokens if t in _WORD_TO_LANG}
    if not found and _DUAL.search(text):  # "Dual Audio" with no language named = Hindi + English
        found = {"hi", "en"}
    return [c for c in LANG_ORDER if c in found]


# ----------------------------------------------------------------------------
# SEASON
# ----------------------------------------------------------------------------
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WORDS_RE = "|".join(_NUM_WORDS)

_S_CODE = re.compile(r"(?<![a-z0-9])s(\d{1,2})(?=e\d|[^a-z0-9]|$)")                  # S01  S1  S01E05
_S_RANGE = re.compile(r"(?<![a-z0-9])s(\d{1,2})\s*[-\u2013]\s*s?(\d{1,2})(?![a-z0-9])")  # S01-S03  S01-03
_S_WORD = re.compile(rf"seasons?[\s._\-]*(?:0*(\d{{1,2}})(?!\d)|({_WORDS_RE})(?![a-z]))")  # Season 1  season one
_S_WORD_RANGE = re.compile(r"seasons?[\s._\-]*0*(\d{1,2})\s*(?:-|\u2013|to)\s*0*(\d{1,2})(?!\d)")  # Seasons 1-3


def detect_seasons(text: str) -> List[int]:
    """[1] for 'S01E05', [1, 2, 3] for 'S01-S03' / 'Season 1-3', [] if no season in the text."""
    t = (text or "").lower()
    found = set()
    for m in _S_CODE.finditer(t):
        found.add(int(m.group(1)))
    for m in _S_WORD.finditer(t):
        found.add(int(m.group(1)) if m.group(1) else _NUM_WORDS[m.group(2)])
    for rx in (_S_RANGE, _S_WORD_RANGE):
        for m in rx.finditer(t):
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= hi <= lo + 30:
                found.update(range(lo, hi + 1))
    return sorted(n for n in found if 1 <= n <= 60)
