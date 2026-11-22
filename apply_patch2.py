"""Kitab-bot feature patch #2 (run AFTER apply_patch.py, inside the repo folder):
   python apply_patch2.py            -> apply
   python apply_patch2.py --check    -> only test if every anchor matches, change nothing
Adds: duplicate hiding, /trending, "Notify me" requests, daily file limit, TMDB poster.
Edits bot.py, i18n.py, .env.example, railway.env (backups saved as *.bak2).

Safe: all changes are prepared in memory first. If ANY required anchor is missing,
nothing is written and the full list of problems is printed."""
import os
import shutil
import sys

BLOCK = r'''# ----------------------------------------------------------------------------
# EXTRAS: duplicate hiding, /trending, "Notify me", daily limit, TMDB poster
# ----------------------------------------------------------------------------
import json as _json

DAILY_LIMIT = int(env("DAILY_LIMIT", "0") or 0)  # files per user per day (IST). 0 = off. Admins are free.
TMDB_API_KEY = env("TMDB_API_KEY")  # optional: poster + rating from themoviedb.org
REQUEST_NOTIFY = env_bool("REQUEST_NOTIFY", "true")  # "Notify me" button when a movie is not found

_top_title: dict = {}      # normalized query -> title of the best result (used for poster / trending)
_search_counts: dict = {}  # title -> how many searches found it
_requests: dict = {}       # normalized query -> [user ids waiting for it]
_daily: dict = {}          # user id -> (date, files sent today)
_tmdb_cache: dict = {}
_note_count = 0


def dedupe(rows):
    """The same file posted twice (same name + size) is shown once."""
    seen, out = set(), []
    for r in rows:
        key = (" ".join(_tokens(r[1])), r[2])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ---- persistence (trending counts + pending requests live in the database meta table)
async def load_extras():
    try:
        _search_counts.update(_json.loads(await store.get_meta("search_counts", "{}") or "{}"))
        _requests.update(_json.loads(await store.get_meta("requests", "{}") or "{}"))
    except Exception as e:
        log.warning("Could not load extras: %s", e)


async def save_extras():
    try:
        await store.set_meta("search_counts", _json.dumps(_search_counts))
        await store.set_meta("requests", _json.dumps(_requests))
    except Exception as e:
        log.warning("Could not save extras: %s", e)


def _bg(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _lang_for(uid: int) -> str:
    """Language of a user who is not talking to the bot right now."""
    lg = _user_lang.get(uid)
    if lg:
        return lg
    saved = await store.get_meta(f"lang:{uid}", "")
    return saved if saved in LANGS else "en"


# ---- daily limit
def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def over_limit(user_id: int) -> bool:
    if DAILY_LIMIT <= 0 or user_id in ALL_ADMINS:
        return False
    day, count = _daily.get(user_id, ("", 0))
    return day == _today() and count >= DAILY_LIMIT


def count_file(user_id: int):
    if DAILY_LIMIT <= 0 or user_id in ALL_ADMINS:
        return
    if len(_daily) > 20000:
        _daily.clear()
    today = _today()
    day, count = _daily.get(user_id, ("", 0))
    _daily[user_id] = (today, count + 1 if day == today else 1)


# ---- trending
def note_search(query: str):
    global _note_count
    qkey = " ".join(norm(to_latin(query)).split())
    top = _top_title.get(qkey)
    key = " ".join(_core(_tokens(top))) if top else qkey
    if not key or len(key) > 60:
        return
    _search_counts[key] = _search_counts.get(key, 0) + 1
    if len(_search_counts) > 3000:
        for k in sorted(_search_counts, key=_search_counts.get)[:1000]:
            _search_counts.pop(k, None)
    _note_count += 1
    if _note_count % 25 == 0:
        _bg(save_extras())


@app.on_message(filters.command("trending") & user_place)
@safe
async def trending_cmd(client: Client, m: Message):
    if not m.from_user:
        return
    lang = await lang_of(m.from_user)
    top = sorted(_search_counts.items(), key=lambda kv: -kv[1])[:10]
    if not top:
        return await m.reply(f"◇ {tr(lang, 'trend_none')}", quote=True)
    lines = [f"{i}. <code>{esc(k.title())}</code> ┃ {c}" for i, (k, c) in enumerate(top, 1)]
    await m.reply(f"☆ <b>{tr(lang, 'trend_title')}</b>\n" + LINE + "\n" + "\n".join(lines) + "\n" + LINE, quote=True)


# ---- "Notify me when available"
def add_request(user_id: int, query: str) -> bool:
    key = " ".join(norm(to_latin(query)).split())
    if not key or len(key) > 60:
        return False
    if key not in _requests and len(_requests) >= 500:
        return False
    if user_id in _requests.get(key, []):
        return False
    if sum(1 for v in _requests.values() if user_id in v) >= 5:
        return False
    _requests.setdefault(key, []).append(user_id)
    _bg(save_extras())
    return True


@app.on_callback_query(filters.regex(r"^nt\|"))
@safe
async def notify_me_cb(client: Client, cq: CallbackQuery):
    lang = await lang_of(cq.from_user)
    query = _search_cache.get(cq.data.split("|", 1)[1])
    if not query:
        return await cq.answer(tr(lang, "a_expired"), show_alert=True)
    ok = add_request(cq.from_user.id, query)
    await cq.answer(tr(lang, "nt_ok" if ok else "nt_dup"), show_alert=True)


async def notify_requesters(title: str):
    """A new file was indexed: tell the users who asked for it."""
    if not _requests:
        return
    hits = [k for k in list(_requests) if strict_filter(k.split(), [(0, title, 0)])]
    if not hits:
        return
    name = " ".join(_core(_tokens(title))).title() or title
    for k in hits:
        for uid in _requests.pop(k, []):
            try:
                text = "🔔 " + tr(await _lang_for(uid), "nt_found", name=esc(name))
                await app.send_message(uid, text, link_preview_options=NO_PREVIEW)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                pass
            await asyncio.sleep(0.1)
    await save_extras()


# ---- TMDB poster (optional)
def _alnum(text: str):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()


def _tmdb_fetch(name: str):
    import urllib.parse
    import urllib.request

    url = "https://api.themoviedb.org/3/search/multi?" + urllib.parse.urlencode(
        {"api_key": TMDB_API_KEY, "query": name}
    )
    with urllib.request.urlopen(url, timeout=8) as resp:
        return _json.loads(resp.read().decode("utf-8"))


async def tmdb_info(name: str):
    key = name.lower()
    if key in _tmdb_cache:
        return _tmdb_cache[key]
    info = None
    try:
        data = await asyncio.to_thread(_tmdb_fetch, name)
        for r in data.get("results", []):
            if r.get("media_type") not in ("movie", "tv") or not r.get("poster_path"):
                continue
            title = r.get("title") or r.get("name") or ""
            if _alnum(title) != _alnum(name):  # only the exact title, never a similar one
                continue
            info = {
                "name": title,
                "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
                "rating": float(r.get("vote_average") or 0),
                "poster": "https://image.tmdb.org/t/p/w500" + r["poster_path"],
            }
            break
    except Exception as e:
        log.warning("TMDB lookup failed (%s)", e)
    if len(_tmdb_cache) > 500:
        _tmdb_cache.clear()
    _tmdb_cache[key] = info
    return info


async def send_results(m: Message, text: str, kb, query: str):
    """Results page. With TMDB_API_KEY the page is sent under the poster of the exact title."""
    if TMDB_API_KEY:
        try:
            top = _top_title.get(" ".join(norm(to_latin(query)).split()))
            info = await tmdb_info(" ".join(_core(_tokens(top)))) if top else None
            if info:
                head = f"☆ <b>{esc(info['name'])}</b>"
                if info["year"]:
                    head += f" ({esc(info['year'])})"
                if info["rating"]:
                    head += f" ┃ ★ {info['rating']:.1f}"
                caption = head + "\n" + text
                if plain_len(caption) <= 1000:
                    return await m.reply_photo(info["poster"], caption=caption, reply_markup=kb, quote=True)
        except Exception as e:
            log.warning("Could not send the poster (%s), sending text instead", e)
    return await m.reply(text, reply_markup=kb, quote=True)


'''

I18N = '''T["en"]["trend_title"] = "Trending Searches"
T["en"]["trend_none"] = "No searches yet."
T["en"]["nt_btn"] = "Notify me when available"
T["en"]["nt_ok"] = "Done! I will message you when it is added."
T["en"]["nt_dup"] = "You already requested this (or your request list is full)."
T["en"]["nt_found"] = "Good news! <b>{name}</b> is now available. Send its name to the bot."
T["en"]["daily_limit"] = "Daily limit reached: {n} files per day. Please try again tomorrow."

T["hi"]["trend_title"] = "ट्रेंडिंग सर्च"
T["hi"]["trend_none"] = "अभी तक कोई सर्च नहीं हुआ।"
T["hi"]["nt_btn"] = "उपलब्ध होने पर बताएँ"
T["hi"]["nt_ok"] = "हो गया! फ़ाइल जुड़ते ही मैं आपको मैसेज करूँगा।"
T["hi"]["nt_dup"] = "आप पहले ही माँग चुके हैं (या आपकी लिस्ट भरी हुई है)।"
T["hi"]["nt_found"] = "खुशखबरी! <b>{name}</b> अब उपलब्ध है। बॉट को उसका नाम भेजें।"
T["hi"]["daily_limit"] = "डेली लिमिट पूरी हो गई: एक दिन में {n} फ़ाइलें। कृपया कल फिर कोशिश करें।"


'''


class Patch:
    """Collects every anchor problem instead of stopping at the first one."""

    def __init__(self, text):
        self.s = text
        self.errors = []
        self.warns = []

    def sub(self, old, new, label, required=True):
        n = self.s.count(old)
        if n == 1:
            self.s = self.s.replace(old, new, 1)
            return True
        (self.errors if required else self.warns).append(f"{label} (found {n} times, need exactly 1)")
        return False


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    shutil.copyfile(p, p + ".bak2")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def build_bot():
    """Returns (new_text or None if already patched, errors, warns)."""
    s = read("bot.py")
    if "def notify_requesters" in s:
        return None, [], []
    if "def strict_filter" not in s:
        return None, ["bot.py has no strict_filter: run apply_patch.py first"], []
    p = Patch(s)

    p.sub('async def build_page(query: str, page: int, token: str, lang: str = "en", group_links: bool = False):',
          BLOCK + 'async def build_page(query: str, page: int, token: str, lang: str = "en", group_links: bool = False):',
          "build_page definition")

    # duplicates + remember the best title
    p.sub("    results = strict_filter(lwords, cand) if STRICT_SEARCH else cand\n    if results:\n        return results, False",
          "    results = strict_filter(lwords, cand) if STRICT_SEARCH else cand\n    results = dedupe(results)\n"
          "    if results:\n        if len(_top_title) > 3000:\n            _top_title.clear()\n"
          "        _top_title[\" \".join(lwords)] = results[0][1]\n        return results, False",
          "run_search strict block")
    p.sub("        results = phonetic_rank(lwords, candidates, min_ratio=0.84, require_all=True)\n        if results:",
          "        results = dedupe(phonetic_rank(lwords, candidates, min_ratio=0.84, require_all=True))\n        if results:",
          "run_search fuzzy block")

    # "Notify me" button on not-found
    p.sub("        rows = []\n        if SUPPORT_USERNAME:\n            rows.append([btn(f\"♡ {tr(lang, 'b_support')}\", BLUE, url=f\"https://t.me/{SUPPORT_USERNAME}\")])",
          "        rows = []\n        if REQUEST_NOTIFY:\n            rows.append([btn(f\"🔔 {tr(lang, 'nt_btn')}\", GREEN, callback_data=f\"nt|{token}\")])\n"
          "        if SUPPORT_USERNAME:\n            rows.append([btn(f\"♡ {tr(lang, 'b_support')}\", BLUE, url=f\"https://t.me/{SUPPORT_USERNAME}\")])",
          "not-found button rows")

    # results with poster + trending count
    p.sub("    reply = await m.reply(text, reply_markup=kb, quote=True)\n    schedule_delete(reply, m)",
          "    note_search(query)\n    reply = await send_results(m, text, kb, query)\n    schedule_delete(reply, m)",
          "do_search end")

    # /trending must not be treated as a movie name + menu entry
    p.sub('"banned", "ping",', '"banned", "ping", "trending",', "search_handler command exclusion list")
    p.sub('        BotCommand("search", "Search a movie: /search name"),',
          '        BotCommand("search", "Search a movie: /search name"),\n        BotCommand("trending", "Most searched movies"),',
          "menu commands", required=False)

    # notify requesters when a file is indexed (in the background, so a scan is not slowed down)
    p.sub('    log.info("Indexed: %s", title)\n    return True',
          '    if _requests:\n        _bg(notify_requesters(title))\n    log.info("Indexed: %s", title)\n    return True',
          "index_message end")

    # daily limit
    p.sub("    log_file_sent(user, title, size)\n    schedule_file_delete(",
          "    log_file_sent(user, title, size)\n    count_file(user.id)\n    schedule_file_delete(", "send_file counter")
    p.sub("    if msg_id is None:\n        return False\n    if not await send_file(client, user, lang, msg_id):",
          "    if msg_id is None:\n        return False\n    if over_limit(user.id):\n"
          "        await client.send_message(chat_id, \"▲ \" + tr(lang, \"daily_limit\", n=DAILY_LIMIT))\n        return True\n"
          "    if not await send_file(client, user, lang, msg_id):", "deliver_pending")
    p.sub("    msg_id = int(cq.data.split(\"|\")[1])\n    if not await send_file(client, cq.from_user, lang, msg_id):\n        return await cq.answer(tr(lang, \"a_filefail\"), show_alert=True)",
          "    msg_id = int(cq.data.split(\"|\")[1])\n    if over_limit(cq.from_user.id):\n"
          "        return await cq.answer(tr(lang, \"daily_limit\", n=DAILY_LIMIT), show_alert=True)\n"
          "    if not await send_file(client, cq.from_user, lang, msg_id):\n        return await cq.answer(tr(lang, \"a_filefail\"), show_alert=True)",
          "again_cb")
    p.sub("    msg_id = int(cq.data.split(\"|\")[1])\n    if not await send_file(client, cq.from_user, lang, msg_id):\n        if cq.message.chat.id < 0 and BOT_USERNAME:",
          "    msg_id = int(cq.data.split(\"|\")[1])\n    if over_limit(cq.from_user.id):\n"
          "        return await cq.answer(tr(lang, \"daily_limit\", n=DAILY_LIMIT), show_alert=True)\n"
          "    if not await send_file(client, cq.from_user, lang, msg_id):\n        if cq.message.chat.id < 0 and BOT_USERNAME:",
          "get_cb")

    # load saved data at startup, save it on shutdown
    p.sub("    _known_users.update(await store.all_user_ids())\n    await app.start()",
          "    _known_users.update(await store.all_user_ids())\n    await load_extras()\n    await app.start()", "main startup")
    p.sub("    await idle()\n    await app.stop()", "    await idle()\n    await save_extras()\n    await app.stop()",
          "main shutdown", required=False)
    return p.s, p.errors, p.warns


def build_i18n():
    s = read("i18n.py")
    if "trend_title" in s:
        return None, []
    p = Patch(s)
    p.sub("class _Safe(dict):", I18N + "class _Safe(dict):", "i18n _Safe class")
    return p.s, p.errors


def build_env(path):
    if not os.path.exists(path):
        return None
    s = read(path)
    if "DAILY_LIMIT" in s:
        return None
    if path.endswith(".env.example"):
        add = ("\n# ===== Extras =====\n# Files per user per day (IST). 0 = off\nDAILY_LIMIT=0\n"
               "# Poster + rating (free key from themoviedb.org). Empty = off\nTMDB_API_KEY=\n"
               "# 'Notify me' button when a movie is not found\nREQUEST_NOTIFY=true\n")
    else:
        add = "DAILY_LIMIT=0\nTMDB_API_KEY=\nREQUEST_NOTIFY=true\n"
    return s.rstrip("\n") + "\n" + add


def main():
    check_only = "--check" in sys.argv
    for need in ("bot.py", "i18n.py"):
        if not os.path.exists(need):
            sys.exit(f"{need} not found. Run this script inside the Kitab-bot folder.")

    bot, bot_err, bot_warn = build_bot()
    i18n, i18n_err = build_i18n()
    errors = bot_err + i18n_err
    if errors:
        print("NOTHING was changed. These anchors did not match:")
        for e in errors:
            print("  x", e)
        sys.exit(1)
    for w in bot_warn:
        print("  (optional part skipped)", w)

    if check_only:
        print("OK: every required anchor matches. Run again without --check to apply.")
        return
    if bot is None and i18n is None:
        print("bot.py / i18n.py: already patched, skipped")
    if bot is not None:
        write("bot.py", bot)
        print("bot.py: patched")
    if i18n is not None:
        write("i18n.py", i18n)
        print("i18n.py: patched")
    for path in (".env.example", "railway.env"):
        env_text = build_env(path)
        if env_text is not None:
            write(path, env_text)
            print(path + ": updated")
    print("Done. Now: git add . && git commit -m 'Extras' && git push")


if __name__ == "__main__":
    main()
