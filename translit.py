"""Script-independent search helpers.

to_latin("मां तुझे सलाम")      -> "maan tujhe salaam"   (Hindi/Marathi/Bengali/Tamil/Telugu... -> English letters)
phonetic_words("maa tujha salam") -> ["m", "tj", "slm"]
phonetic_words("मां तुझे सलाम")   -> ["m", "tj", "slm"]   (same key, so the two spellings match)

Other scripts (Arabic, Cyrillic, Korean, Chinese ...) are converted with the optional `unidecode`
package (pip install unidecode). Without it only Indic scripts are converted.
"""
import re
import unicodedata

try:  # optional
    from unidecode import unidecode as _unidecode
except Exception:  # pragma: no cover
    _unidecode = None

# All Indic Unicode blocks (Devanagari 0900 ... Malayalam 0D00) have the same letter layout, so one
# table (offset inside the block, written for Devanagari) works for every one of them.
_LO, _HI = 0x0900, 0x0D80

_VOW = {
    0x05: "a", 0x06: "aa", 0x07: "i", 0x08: "ee", 0x09: "u", 0x0A: "oo", 0x0B: "ri", 0x0C: "li",
    0x0D: "e", 0x0E: "e", 0x0F: "e", 0x10: "ai", 0x11: "o", 0x12: "o", 0x13: "o", 0x14: "au",
}
_CON = {
    0x15: "k", 0x16: "kh", 0x17: "g", 0x18: "gh", 0x19: "n", 0x1A: "ch", 0x1B: "chh", 0x1C: "j",
    0x1D: "jh", 0x1E: "n", 0x1F: "t", 0x20: "th", 0x21: "d", 0x22: "dh", 0x23: "n", 0x24: "t",
    0x25: "th", 0x26: "d", 0x27: "dh", 0x28: "n", 0x29: "n", 0x2A: "p", 0x2B: "ph", 0x2C: "b",
    0x2D: "bh", 0x2E: "m", 0x2F: "y", 0x30: "r", 0x31: "r", 0x32: "l", 0x33: "l", 0x34: "l",
    0x35: "v", 0x36: "sh", 0x37: "sh", 0x38: "s", 0x39: "h",
}
_MAT = {
    0x3E: "aa", 0x3F: "i", 0x40: "ee", 0x41: "u", 0x42: "oo", 0x43: "ri", 0x44: "ri", 0x45: "e",
    0x46: "e", 0x47: "e", 0x48: "ai", 0x49: "o", 0x4A: "o", 0x4B: "o", 0x4C: "au",
}
_VIRAMA = 0x4D
_NUKTA = 0x3C
_INH = "\x00"  # marks an inherent 'a' (so the final one can be dropped: kamal, not kamala)


def _indic_off(ch: str):
    cp = ord(ch)
    return (cp & 0x7F) if _LO <= cp < _HI else None


def _convert_indic(text: str, nasal: bool) -> str:
    text = "".join(c for c in text if _indic_off(c) != _NUKTA)
    out, i, n = [], 0, len(text)
    while i < n:
        off = _indic_off(text[i])
        if off is None:
            out.append(text[i])
            i += 1
        elif off in _CON:
            syl = _CON[off]
            i += 1
            noff = _indic_off(text[i]) if i < n else None
            if noff in _MAT:
                out.append(syl + _MAT[noff])
                i += 1
            elif noff == _VIRAMA:
                out.append(syl)
                i += 1
            else:
                out.append(syl + _INH)
        elif off in _VOW:
            out.append(_VOW[off])
            i += 1
        elif off in (0x01, 0x02):  # chandrabindu / anusvara
            if nasal:
                out.append("n")
            i += 1
        elif off == 0x03:  # visarga
            out.append("h")
            i += 1
        elif 0x66 <= off <= 0x6F:  # digits
            out.append(str(off - 0x66))
            i += 1
        elif off == 0x50:  # om
            out.append("om")
            i += 1
        else:  # stray matra, virama, danda ...
            out.append(" " if off in (0x64, 0x65) else "")
            i += 1
    s = "".join(out)
    s = re.sub(_INH + r"(?=[^a-z" + _INH + r"]|$)", "", s)  # final schwa: kamal
    s = re.sub(r"(?<=[aeiou][bcdfghjklmnpqrstvwxyz])" + _INH + r"(?=[bcdfghjklmnpqrstvwxyz][aeiou])", "", s)  # samjha
    return s.replace(_INH, "a")


def to_latin(text: str, nasal: bool = True) -> str:
    """Any text -> lowercase letters a-z (+ digits, spaces). Latin text is returned as is."""
    text = unicodedata.normalize("NFC", text or "").lower()
    if any(_LO <= ord(c) < _HI for c in text):
        text = _convert_indic(text, nasal)
    if not text.isascii() and _unidecode:
        text = _unidecode(text).lower()
    return text


_SK = str.maketrans({"f": "p", "w": "v", "z": "j", "q": "k", "c": "k", "x": "k"})


def phonetic_words(text: str):
    """Consonant skeleton of every word, the same for different spellings of the same sound:
    salam / salaam / सलाम -> 'slm',  tujha / tujhe / तुझे -> 'tj'."""
    s = to_latin(text, nasal=False)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"(?<=[bcdfghjklmnpqrstvwxyz])h", "", s)  # kh gh ch sh th ph -> k g c s t p
    s = s.translate(_SK)
    s = re.sub(r"[aeiou]", "", s)
    words = [re.sub(r"(.)\1+", r"\1", w) for w in s.split()]
    return [w for w in words if w]


def phonetic_key(text: str) -> str:
    """String saved in the database (skey column) for phonetic matching."""
    return " ".join(phonetic_words(text))
