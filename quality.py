"""Detects quality (1080p...), language (Hindi, Tamil...) and season (S01...) from file names."""
import re
from collections import OrderedDict
from typing import Iterable, List, Optional, Tuple

# ----------------------------------------------------------------------------
# QUALITY
# ----------------------------------------------------------------------------
ORDER = ["2160p", "1440p", "1080p", "720p", "576p", "480p", "360p", "240p"]  # high -> low

_RES = r"(2160|1440|1080|720|576|480|360|240)"
_P = re.compile(rf"(?<!\d){_RES}p", re.I)                # 1080p  720P  480p
_X = re.compile(rf"\d{{3,4}}\s?x\s?{_RES}(?!\d)", re.I)  # 1920x1080
_K = re.compile(r"(?<![a-z0-9])(4k|uhd)(?![a-z0-9])", re.I)


def detect_quality(text: str) -> Optional[str]:
    """'1080p' if the file name mentions a quality, else None."""
    text = text or ""
    m = _P.search(text) or _X.search(text)
    if m:
        return f"{m.group(1)}p"
    if _K.search(text):
        return "2160p"
    return None


def quality_counts(titles: Iterable[str]) -> "OrderedDict[str, int]":
    found = {}
    for t in titles:
        q = detect_quality(t)
        if q:
            found[q] = found.get(q, 0) + 1
    return OrderedDict(sorted(found.items(), key=lambda kv: ORDER.index(kv[0])))


# ----------------------------------------------------------------------------
# LANGUAGE
# code -> (button name, regex). Short forms (hin/eng/tam/tel) are only used for the big languages.
# ----------------------------------------------------------------------------
LANGS = OrderedDict(
    [
        ("hin", ("Hindi", r"hindi|hin")),
        ("eng", ("English", r"english|eng")),
        ("tam", ("Tamil", r"tamil|tam")),
        ("tel", ("Telugu", r"telugu|tel")),
        ("mal", ("Malayalam", r"malayalam")),
        ("kan", ("Kannada", r"kannada")),
        ("ben", ("Bengali", r"bengali|bangla")),
        ("mar", ("Marathi", r"marathi")),
        ("pun", ("Punjabi", r"punjabi")),
        ("guj", ("Gujarati", r"gujarati")),
        ("bho", ("Bhojpuri", r"bhojpuri")),
        ("urd", ("Urdu", r"urdu")),
        ("odi", ("Odia", r"odia|oriya")),
        ("dual", ("Dual Audio", r"dual\s?audio")),
        ("multi", ("Multi Audio", r"multi\s?(?:audio|lang\w*)")),
    ]
)
LANG_ORDER = list(LANGS)
LANG_NAMES = {code: name for code, (name, _) in LANGS.items()}
_LANG_RE = {
    code: re.compile(rf"(?<![a-z0-9])(?:{pat})(?![a-z0-9])") for code, (_, pat) in LANGS.items()
}
# "English Subs", "Hindi Subtitles" are subtitles, not the audio language
_SUB_RE = re.compile(
    r"(?<![a-z0-9])(?:hindi|hin|english|eng|tamil|tam|telugu|tel|malayalam|kannada|bengali|bangla|"
    r"marathi|punjabi|gujarati|bhojpuri|urdu|odia|oriya)\s?sub(?:s|bed|titles?)?(?![a-z0-9])"
)


def _norm(text: str) -> str:
    return re.sub(r"[._\-\[\]\(\)\+,&/]+", " ", (text or "").lower())


def detect_languages(text: str) -> List[str]:
    t = _SUB_RE.sub(" ", _norm(text))
    return [code for code, rx in _LANG_RE.items() if rx.search(t)]


# ----------------------------------------------------------------------------
# SEASON
# ----------------------------------------------------------------------------
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10}
_S_RANGE = re.compile(r"(?<![a-z0-9])s(?:eason)?\s?(\d{1,2})\s?(?:-|to)\s?s?(?:eason)?\s?(\d{1,2})(?!\d)")
_S_ONE = re.compile(r"(?<![a-z0-9])(?:season[\s._]?|s)(\d{1,2})(?!\d)")
_S_WORD = re.compile(r"(?<![a-z0-9])season[\s._]?(" + "|".join(_WORDS) + r")(?![a-z])")


def detect_seasons(text: str) -> List[int]:
    """S01, S1, S01E05, Season 2, Season.02, Season two, S01-S03 -> [1], [2], [1, 2, 3]"""
    t = (text or "").lower()
    found = set()
    for a, b in _S_RANGE.findall(t):
        a, b = int(a), int(b)
        if 1 <= a <= b <= 50 and b - a <= 30:
            found.update(range(a, b + 1))
    for n in _S_ONE.findall(t):
        if 1 <= int(n) <= 50:
            found.add(int(n))
    for w in _S_WORD.findall(t):
        found.add(_WORDS[w])
    return sorted(found)


def file_meta(title: str) -> Tuple[Optional[str], set, set]:
    """(quality, {language codes}, {season numbers}) of a file name."""
    return detect_quality(title), set(detect_languages(title)), set(detect_seasons(title))
