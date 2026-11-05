"""Understands names written in other scripts and in different spellings.

- to_latin("मां तुझे सलाम")  -> "man tujhe salam"      (Hindi, Marathi, Bengali, Gujarati, Punjabi,
                                                         Odia, Tamil, Telugu, Kannada, Malayalam)
- other scripts (Arabic, Persian, Urdu, Russian, Hebrew, Korean, Chinese ...) use the optional
  `Unidecode` package (pip install Unidecode). Without it only the Indian scripts are converted.
- phonetic_rank(words, candidates): finds titles even when the spelling is different
  ("salam" = "salaam", "maan" = "maa", "tujhe" = "tujhhe").
"""
import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Tuple

try:  # optional
    from unidecode import unidecode as _unidecode
except Exception:  # pragma: no cover
    _unidecode = None

# ----------------------------------------------------------------------------
# Brahmic scripts: every block has the same layout as Devanagari, so we shift the
# character back into the Devanagari block and convert it with one table.
# ----------------------------------------------------------------------------
_BLOCKS = [0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80, 0x0C00, 0x0C80, 0x0D00]


def _to_deva(ch: str):
    """Devanagari-equivalent of a Brahmic character, or None if it is not one."""
    o = ord(ch)
    for base in _BLOCKS:
        if base <= o < base + 0x80:
            return chr(0x0900 + o - base)
    return None


_VOW = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai",
        "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e", "ऎ": "e", "ऒ": "o"}
_MAT = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
        "ौ": "au", "ॉ": "o", "ॅ": "e", "ॆ": "e", "ॊ": "o"}
_CON = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
        "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
        "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
        "ल": "l", "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ऩ": "n", "ऱ": "r",
        "ऴ": "l"}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f"}
_NASAL = "ंँ"
_VIRAMA = "\u094d"
_NUKTA_CH = "\u093c"
_ZWJ = "\u200c\u200d"


def _is_letter(ch: str) -> bool:
    return ch in _CON or ch in _VOW or ch in _MAT or ch in _NASAL or ch == "ः"


def _deva_to_latin(text: str, keep_final_a: bool = False) -> str:
    text = text.replace("ज्ञ", "ग्य")  # gya
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _CON:
            base = _CON[ch]
            j = i + 1
            if j < n and text[j] == _NUKTA_CH:
                base = _NUKTA.get(ch, base)
                j += 1
            if j < n and text[j] in _MAT:
                out.append(base + _MAT[text[j]])
                i = j + 1
            elif j < n and text[j] == _VIRAMA:
                out.append(base)
                i = j + 1
            else:
                # inherent "a", but not at the end of a word (सलाम -> salam, not salama)
                k = j
                while k < n and text[k] in _ZWJ:
                    k += 1
                out.append(base + ("a" if keep_final_a or (k < n and _is_letter(text[k])) else ""))
                i = j
        elif ch in _VOW:
            out.append(_VOW[ch])
            i += 1
        elif ch in _NASAL:
            out.append("n")
            i += 1
        elif ch == "ः":
            out.append("h")
            i += 1
        elif "०" <= ch <= "९":
            out.append(str(ord(ch) - ord("०")))
            i += 1
        elif ch in (_VIRAMA, _NUKTA_CH) or ch in _ZWJ:
            i += 1
        elif ch in "।॥":
            out.append(" ")
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def to_latin(text: str) -> str:
    """Writes the text in Latin letters (unchanged if it already is)."""
    if not text or text.isascii():
        return text
    out: List[str] = []
    run: List[str] = []
    south = False  # Tamil/Telugu/Kannada/Malayalam keep the final "a" (Pushpa), Hindi drops it (Salam)
    for ch in text:
        deva = _to_deva(ch) if ord(ch) >= 0x0900 else None
        if deva is not None:
            if not run:
                south = 0x0B80 <= ord(ch) < 0x0D80
            run.append(deva)
            continue
        if run:
            out.append(_deva_to_latin("".join(run), south))
            run = []
        out.append(ch)
    if run:
        out.append(_deva_to_latin("".join(run), south))
    result = "".join(out)
    if not result.isascii():
        if _unidecode:
            result = _unidecode(result)
        else:  # é -> e ; scripts we can't convert are dropped
            result = unicodedata.normalize("NFKD", result).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", result).strip()


# ----------------------------------------------------------------------------
# Spelling-tolerant matching
# ----------------------------------------------------------------------------
_SUBS = (("ph", "f"), ("sh", "s"), ("ch", "C"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("gh", "g"),
         ("jh", "j"), ("kh", "k"), ("ck", "k"), ("q", "k"), ("x", "ks"), ("c", "k"), ("w", "v"),
         ("z", "j"), ("y", "i"), ("o", "u"), ("e", "i"))


def phon(word: str) -> str:
    """Sound-alike key: maan/man, salam/salaam, tujhe/tujhhe/tuje all end up (nearly) the same."""
    w = re.sub(r"[^a-z0-9]", "", (word or "").lower())
    w = re.sub(r"(.)\1+", r"\1", w)  # aa -> a, ee -> e, ll -> l
    for a, b in _SUBS:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def _skeleton(key: str) -> str:
    return re.sub(r"[aiu]", "", key)


def _sim(qk: str, tk: str) -> float:
    if qk == tk:
        return 1.0
    if min(len(qk), len(tk)) <= 2:  # very short words: only "ma" ~ "man" style differences
        close = abs(len(qk) - len(tk)) <= 1 and (qk.startswith(tk) or tk.startswith(qk))
        return 0.85 if close else 0.0
    best = SequenceMatcher(None, qk, tk).ratio()
    qs, ts = _skeleton(qk), _skeleton(tk)
    if len(qs) >= 3 and len(ts) >= 3:  # same consonants (e.g. Urdu/Arabic without vowels)
        best = max(best, SequenceMatcher(None, qs, ts).ratio() * 0.95)
    return best


def phonetic_rank(
    words: Iterable[str],
    candidates: Iterable[Tuple[int, str, int]],
    min_ratio: float = 0.78,
    limit: int = 200,
) -> List[Tuple[int, str, int]]:
    """Orders candidate files by how well their name sounds like the query words."""
    qkeys = [k for k in (phon(w) for w in words) if k]
    if not qkeys:
        return []
    need = len(qkeys) if len(qkeys) <= 2 else max(2, math.ceil(len(qkeys) * 0.67))
    scored = []
    for mid, title, size in candidates:
        tokens = [phon(t) for t in re.findall(r"[a-z0-9]+", to_latin(title or "").lower())]
        tokens = [t for t in tokens if t]
        hits, total = 0, 0.0
        for qk in qkeys:
            best = max((_sim(qk, tk) for tk in tokens), default=0.0)
            if best >= min_ratio:
                hits += 1
                total += best
        if hits >= need:
            scored.append((-total, title or "", mid, size))
    scored.sort()
    return [(mid, title, size) for _, title, mid, size in scored[:limit]]
