"""Strict-search patch for Kitab-bot.
Run inside the repo folder:  python apply_patch.py
Edits bot.py, translit.py, i18n.py, .env.example, railway.env (backups are saved as *.bak)."""
import os
import re
import shutil
import sys

BOT_BLOCK = '''# ----------------------------------------------------------------------------
# STRICT SEARCH: only the movie/series that was typed (whole names), no "related" titles
# ----------------------------------------------------------------------------
STRICT_SEARCH = env_bool("STRICT_SEARCH", "true")
SUGGEST = env_bool("SUGGEST", "true")

_META_RE = re.compile(
    r"^(?:19\\d\\d|20\\d\\d|s\\d{1,2}(?:e\\d{1,3})?|e\\d{1,3}|ep\\d{1,3}|season\\d*|part\\d*|\\d{3,4}p|4k|uhd|"
    r"hdrip|webrip|web|webdl|bluray|bdrip|brrip|hdtv|hdcam|hdts|camrip|dvdrip|x264|x265|h264|h265|hevc|10bit|"
    r"hindi|english|tamil|telugu|malayalam|kannada|bengali|dual|multi|audio|complete|series|"
    r"mkv|mp4|avi|esub|esubs|sub|subs|nf|amzn|dl)$"
)


def _tokens(title: str):
    toks = norm(to_latin(title or "")).split()
    return [t for t in toks if not t.startswith(("@", "http", "www"))]


def _core(toks):
    """Title part only: 'money heist s01e01 720p' -> ['money', 'heist']"""
    core = []
    for t in toks:
        if _META_RE.match(t):
            break
        core.append(t)
    return core or toks


def strict_filter(q, rows):
    """Returns only the best matching level:
    1) title == query   2) query is a whole phrase inside the title   3) every query word is a whole word."""
    if not q or not rows:
        return []
    n = len(q)
    t1, t2, t3 = [], [], []
    for r in rows:
        toks = _tokens(r[1])
        core = _core(toks)
        if core == q:
            t1.append(r)
        elif any(core[i:i + n] == q for i in range(len(core) - n + 1)):
            t2.append(r)
        elif all(w in toks for w in q):
            t3.append(r)
    return t1 or t2 or t3


async def suggest_names(query: str, limit: int = 3):
    """'Did you mean' names: only spelling mistakes of the WHOLE query (never partial/related titles)."""
    latin = to_latin(query)
    lw = norm(latin).split()
    if not lw:
        return []
    prefixes = list({w[:3] for w in lw if len(w) >= 2})
    cands = await store.find_any(prefixes, limit=800) if prefixes else []
    names = []
    for _, title, _ in phonetic_rank(lw, cands, min_ratio=0.7, require_all=True):
        name = " ".join(_core(_tokens(title))).title()
        if name and not any(name == x or name.startswith(x + " ") for x in names):
            names.append(name)
        if len(names) >= limit:
            break
    return names


async def run_search(query: str):
    """(results, fuzzy). Whole-name matching: only what the user typed, never 'related' titles."""
    words = norm(query).split()
    latin = to_latin(query)
    lwords = norm(latin).split() if latin != query else words

    cand = await store.find(words)
    if lwords and lwords != words:
        seen = {r[0] for r in cand}
        cand += [r for r in await store.find(lwords) if r[0] not in seen]

    results = strict_filter(lwords, cand) if STRICT_SEARCH else cand
    if results:
        return results, False

    # typo tolerance: EVERY word of the query must sound alike (no single-word matches any more)
    if lwords:
        prefixes = list({w[:3] for w in lwords if len(w) >= 2})
        candidates = await store.find_any(prefixes, limit=800) if prefixes else []
        results = phonetic_rank(lwords, candidates, min_ratio=0.84, require_all=True)
        if results:
            return results, True
    return [], False

'''

NOT_FOUND = '''def not_found_text(query: str, lang: str = "en", suggestions=None) -> str:
    text = (
        f"¤ <b>{tr(lang, 'nf_title')}</b>\\n"
        + LINE
        + f"\\n¤ <i>{esc(query[:60])}</i>\\n\\n"
        f"♤ <b>{tr(lang, 'nf_try')}:</b>\\n"
        f"• {tr(lang, 'nf1')}\\n"
        f"• {tr(lang, 'nf2')}\\n"
        f"• {tr(lang, 'nf3')}\\n"
    )
    if suggestions:
        text += f"\\n☆ <b>{tr(lang, 'nf_mean')}</b>\\n" + "\\n".join(
            f"<code>{esc(s)}</code>" for s in suggestions
        ) + "\\n"
    return text + LINE


'''

OLD_REPLY = '''        reply = await m.reply(
            not_found_text(query, lang),
            reply_markup=InlineKeyboardMarkup(rows),
            quote=True,
        )'''
NEW_REPLY = '''        sugg = await suggest_names(query) if SUGGEST else []
        reply = await m.reply(
            not_found_text(query, lang, sugg),
            reply_markup=InlineKeyboardMarkup(rows),
            quote=True,
        )'''


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    shutil.copyfile(p, p + ".bak")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def patch_bot():
    s = read("bot.py")
    if "def strict_filter" in s:
        print("bot.py: already patched, skipped")
        return
    s, n = re.subn(r"async def run_search\(query: str\):.*?(?=\nasync def build_page\()",
                   lambda m: BOT_BLOCK, s, count=1, flags=re.S)
    assert n == 1, "run_search not found in bot.py"
    s, n = re.subn(r"def not_found_text\(.*?\n\n\n(?=@app\.on_message)", lambda m: NOT_FOUND, s, count=1, flags=re.S)
    assert n == 1, "not_found_text not found in bot.py"
    assert OLD_REPLY in s, "not-found reply block not found in bot.py"
    s = s.replace(OLD_REPLY, NEW_REPLY, 1)
    write("bot.py", s)
    print("bot.py: patched")


def patch_translit():
    s = read("translit.py")
    if "require_all" in s:
        print("translit.py: already patched, skipped")
        return
    old_sig = "    limit: int = 200,\n) -> List[Tuple[int, str, int]]:"
    new_sig = "    limit: int = 200,\n    require_all: bool = False,\n) -> List[Tuple[int, str, int]]:"
    old_need = "    need = len(qkeys) if len(qkeys) <= 2 else max(2, math.ceil(len(qkeys) * 0.67))"
    new_need = "    need = len(qkeys) if (require_all or len(qkeys) <= 2) else max(2, math.ceil(len(qkeys) * 0.67))"
    assert old_sig in s and old_need in s, "phonetic_rank anchors not found in translit.py"
    write("translit.py", s.replace(old_sig, new_sig, 1).replace(old_need, new_need, 1))
    print("translit.py: patched")


def patch_i18n():
    s = read("i18n.py")
    if "nf_mean" in s:
        print("i18n.py: already patched, skipped")
        return
    anchor = "class _Safe(dict):"
    assert anchor in s, "anchor not found in i18n.py"
    write("i18n.py", s.replace(anchor, 'T["en"]["nf_mean"] = "Did you mean"\n\n\n' + anchor, 1))
    print("i18n.py: patched")


def patch_env(path):
    if not os.path.exists(path):
        return
    s = read(path)
    if "STRICT_SEARCH" in s:
        print(path + ": already has STRICT_SEARCH, skipped")
        return
    add = "\n# true = only the exact movie that was typed (no related titles)\nSTRICT_SEARCH=true\nSUGGEST=true\n"
    if path.endswith(".env.example"):
        add = "\n# ===== Strict search: only the exact name typed, no related titles =====\nSTRICT_SEARCH=true\nSUGGEST=true\n"
    else:
        add = "STRICT_SEARCH=true\nSUGGEST=true\n"
    write(path, s.rstrip("\n") + "\n" + add)
    print(path + ": updated")


if __name__ == "__main__":
    for need in ("bot.py", "translit.py", "i18n.py"):
        if not os.path.exists(need):
            sys.exit(f"{need} not found. Run this script inside the Kitab-bot folder.")
    patch_bot()
    patch_translit()
    patch_i18n()
    patch_env(".env.example")
    patch_env("railway.env")
    print("Done. Now: git add . && git commit -m 'Strict search' && git push")
