"""Kitab-bot TMDB fix (patch #4). Run AFTER apply_patch.py, apply_patch2.py and apply_patch3.py:
   python apply_patch4.py
Fixes: v4 token support, smarter title match (KGF = K.G.F), no caching of errors,
poster is downloaded and uploaded (no URL problems), new admin command /tmdb for diagnosis.
Edits bot.py only (backup: bot.py.bak4)."""
import os
import re
import shutil
import sys

NEW_SECTION = r'''# ---- TMDB poster (optional)  [v2]
def _alnum(text: str) -> str:
    """'K.G.F: Chapter 2' -> 'kgfchapter2' (so KGF = K.G.F, Grey's = Greys)"""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower().replace("'", ""))


def _tmdb_kind() -> str:
    key = TMDB_API_KEY.strip()
    return "v4" if (key.startswith("eyJ") or len(key) > 60) else "v3"


def _tmdb_get(path: str, params: dict):
    import urllib.parse
    import urllib.request

    key = TMDB_API_KEY.strip()
    headers = {"User-Agent": "Mozilla/5.0 (KitabBot)", "Accept": "application/json"}
    query = dict(params)
    if _tmdb_kind() == "v4":  # "API Read Access Token" (long, starts with eyJ)
        headers["Authorization"] = "Bearer " + key
    else:  # "API Key" (32 characters)
        query["api_key"] = key
    url = "https://api.themoviedb.org/3" + path + "?" + urllib.parse.urlencode(query)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as resp:
        return _json.loads(resp.read().decode("utf-8"))


def _fetch_bytes(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KitabBot)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _tmdb_pick(results, name: str, year: str = ""):
    """The result whose title is EXACTLY the wanted name (any of its 4 title fields), same year preferred."""
    want = _alnum(name)
    matches = []
    for r in results or []:
        if r.get("media_type") not in ("movie", "tv") or not r.get("poster_path"):
            continue
        titles = {_alnum(r.get(k)) for k in ("title", "name", "original_title", "original_name")}
        if want and want in titles:
            matches.append(r)
    if not matches:
        return None
    if year:
        for r in matches:
            if (r.get("release_date") or r.get("first_air_date") or "")[:4] == year:
                return r
    return matches[0]


async def tmdb_info(name: str, year: str = ""):
    ckey = f"{name.lower()}|{year}"
    if ckey in _tmdb_cache:
        return _tmdb_cache[ckey]
    # an error is NOT cached (it raises), only real answers are
    data = await asyncio.to_thread(_tmdb_get, "/search/multi", {"query": name, "include_adult": "false"})
    r = _tmdb_pick(data.get("results"), name, year)
    info = None
    if r:
        info = {
            "name": r.get("title") or r.get("name") or name,
            "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
            "rating": float(r.get("vote_average") or 0),
            "poster": "https://image.tmdb.org/t/p/w500" + r["poster_path"],
        }
    else:
        log.info("TMDB: no exact title match for '%s'", name)
    if len(_tmdb_cache) > 500:
        _tmdb_cache.clear()
    _tmdb_cache[ckey] = info
    return info


async def send_results(m: Message, text: str, kb, query: str):
    """Results page. With TMDB_API_KEY the page is sent under the poster of the exact title."""
    if TMDB_API_KEY:
        try:
            top = _top_title.get(" ".join(_words(query)))
            info = None
            if top:
                toks = _tokens(top)
                year = next((t for t in toks if re.fullmatch(r"(?:19|20)\d\d", t)), "")
                info = await tmdb_info(" ".join(_core(toks)), year)
            if info:
                head = f"☆ <b>{esc(info['name'])}</b>"
                if info["year"]:
                    head += f" ({esc(info['year'])})"
                if info["rating"]:
                    head += f" ┃ ★ {info['rating']:.1f}"
                caption = head + "\n" + text
                if plain_len(caption) <= 1000:
                    try:
                        photo = io.BytesIO(await asyncio.to_thread(_fetch_bytes, info["poster"]))
                        photo.name = "poster.jpg"
                    except Exception as e:
                        log.warning("Could not download the poster (%s), sending its link", e)
                        photo = info["poster"]
                    return await m.reply_photo(photo, caption=caption, reply_markup=kb, quote=True)
        except Exception as e:
            log.warning("TMDB poster failed: %s: %s", type(e).__name__, e)
    return await m.reply(text, reply_markup=kb, quote=True)


@app.on_message(filters.command("tmdb") & admin_place & admin_filter)
@safe
async def tmdb_cmd(client: Client, m: Message):
    """/tmdb Money Heist  ->  tells why the poster does or does not appear."""
    import urllib.error

    name = m.text.split(None, 1)[1].strip() if len(m.command) > 1 else "Money Heist"
    if not TMDB_API_KEY:
        return await m.reply(
            "✗ <b>TMDB_API_KEY is empty.</b>\nAdd it in the Railway Variables tab (exact name "
            "<code>TMDB_API_KEY</code>) and redeploy.",
            quote=True,
        )
    lines = [f"◇ Key type: <b>{_tmdb_kind()}</b> ({len(TMDB_API_KEY.strip())} characters)"]
    try:
        data = await asyncio.to_thread(_tmdb_get, "/search/multi", {"query": name, "include_adult": "false"})
        results = data.get("results", [])
        lines.append(f"✓ TMDB answered: {len(results)} result(s) for <i>{esc(name)}</i>")
        for r in results[:5]:
            lines.append(
                f"   • {esc(r.get('title') or r.get('name') or '?')} ({esc(r.get('media_type'))}) "
                f"{'🖼' if r.get('poster_path') else '✗ no poster'}"
            )
        pick = _tmdb_pick(results, name)
        if pick:
            lines.append(f"✓ Exact match: <b>{esc(pick.get('title') or pick.get('name'))}</b> → poster will be shown")
        else:
            lines.append("✗ No result has exactly this title, so the bot sends the plain text page (by design).")
    except urllib.error.HTTPError as e:
        hint = {401: "key is wrong or expired", 404: "wrong address", 429: "too many requests"}.get(e.code, "")
        lines.append(f"✗ TMDB said HTTP {e.code} {hint}")
    except Exception as e:
        lines.append(f"✗ {esc(type(e).__name__)}: {esc(e)}")
    await m.reply("☆ <b>TMDB Check</b>\n" + LINE + "\n" + "\n".join(lines), quote=True)


'''


def sub(s, old, new, label):
    assert s.count(old) == 1, f"anchor not found (or not unique): {label}"
    return s.replace(old, new, 1)


def main():
    if not os.path.exists("bot.py"):
        sys.exit("bot.py not found. Run this script inside the Kitab-bot folder.")
    with open("bot.py", encoding="utf-8") as f:
        s = f.read()
    if "def tmdb_cmd" in s:
        print("bot.py: already patched, skipped")
        return
    assert "def _words(" in s and "def notify_requesters" in s, "Run apply_patch.py, apply_patch2.py and apply_patch3.py first."

    s, n = re.subn(r"# ---- TMDB poster \(optional\)\n.*?(?=async def build_page\()", lambda m: NEW_SECTION, s, count=1, flags=re.S)
    assert n == 1, "TMDB section not found"
    s = sub(s, 'r"mkv|mp4|avi|esub|esubs|sub|subs|nf|amzn|dl)$"',
            'r"mkv|mp4|avi|esub|esubs|sub|subs|nf|amzn|dl|dubbed|dub|org|uncut|extended|proper|repack|remastered|imax|hq|hdtc|predvd)$"',
            "meta words")
    s = sub(s, '"ping", "trending",', '"ping", "trending", "tmdb",', "command exclusion list")
    s = sub(s, '        BotCommand("ping", "Is the bot alive?"),',
            '        BotCommand("ping", "Is the bot alive?"),\n        BotCommand("tmdb", "Check the TMDB poster setup"),', "menu")

    shutil.copyfile("bot.py", "bot.py.bak4")
    with open("bot.py", "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print("bot.py: patched. Now: git add . && git commit -m 'TMDB fix' && git push")


if __name__ == "__main__":
    main()
