"""Kitab-bot feature patch #5: /trending command + movie rating on every file
(run inside the repo folder, next to bot.py and ratings.py):
   python apply_patch5.py

What it does
  * /trending      -> top 10 trending movies + top 10 trending series with ratings (TMDB list, IMDb rating via OMDb)
  * file caption   -> the rating of the movie/series is added under the file size
  * /trending is added to the command menu and the Help page
Edits bot.py and .env.example only (backup: bot.py.bak5). Safe: if one of the important places
is not found, NOTHING is changed. All the network code lives in the new file ratings.py."""
import os
import shutil
import sys

HANDLER = r'''# ----------------------------------------------------------------------------
# /trending : top 10 trending movies + top 10 trending series with ratings
# (list from TMDB, IMDb rating from OMDb: see ratings.py and .env.example)
# ----------------------------------------------------------------------------
@app.on_message(filters.command("trending") & user_place)
@safe
async def trending_cmd(client: Client, m: Message):
    if not m.from_user or flood_blocked(m.from_user.id):
        return
    private = m.chat.id > 0
    if private:
        await register_user(m.from_user.id)
    lang = await lang_of(m.from_user)
    if private:  # in a group the join check happens when a file is opened
        missing = await not_joined(client, m.from_user.id)
        if missing:
            text, kb = await join_view(missing, lang)
            return await m.reply(text, reply_markup=kb, quote=True)

    if not ratings.trending_enabled():
        if is_admin_id(m.from_user.id):
            return await m.reply(
                "▲ <b>/trending is not set up yet.</b>\n"
                "Add <code>TMDB_API_KEY</code> (free, themoviedb.org) to the environment variables and restart. "
                "Optional: <code>OMDB_API_KEY</code> (free, omdbapi.com) for real IMDb ratings.",
                quote=True,
            )
        return await m.reply(ratings.t(lang, "t_fail"), quote=True)

    wait = await m.reply(f"◇ {ratings.t(lang, 't_wait')}", quote=True)
    try:
        data = await ratings.get_trending()
    except Exception as e:
        log.warning("Trending list failed: %s: %s", type(e).__name__, e)
        await edit(wait, f"▲ {ratings.t(lang, 't_fail')}")
        schedule_delete(wait, m)
        return
    kb = InlineKeyboardMarkup([[btn(f"× {tr(lang, 'b_close')} ×", RED, callback_data="close")]])
    await edit(wait, ratings.trending_text(data, lang), kb)
    schedule_delete(wait, m)


'''

ENV_BLOCK = """
# ===== /trending + movie rating (optional, dono key FREE hain) =====
# TMDB: trending list ke liye. themoviedb.org -> Settings -> API -> "Developer" key banao
TMDB_API_KEY=
# OMDb: asli IMDb rating ke liye. omdbapi.com/apikey.aspx (free = 1000 requests/din, key email par aati hai)
OMDB_API_KEY=
# Optional: TRENDING_WINDOW=week (ya day) | TRENDING_COUNT=10 | TRENDING_CACHE_MIN=360
# Optional: FILE_RATING=true (file ke caption me rating) | RATING_TIMEOUT=4 (seconds) | RATING_PREFETCH=2
"""


def sub(s, old, new, label, optional=False):
    found = s.count(old)
    if found != 1:
        if optional:
            print(f"  skipped (place not found, not important): {label}")
            return s
        sys.exit(f"STOP: place not found (or found {found} times): {label}\nbot.py was NOT changed.")
    print(f"  ok: {label}")
    return s.replace(old, new, 1)


def main():
    if not os.path.exists("bot.py"):
        sys.exit("bot.py not found. Run this script inside the Kitab-bot folder.")
    if not os.path.exists("ratings.py"):
        sys.exit("ratings.py not found. Put ratings.py next to bot.py first.")
    with open("bot.py", encoding="utf-8") as f:
        s = f.read()
    if "def trending_cmd(" in s:
        print("bot.py: already patched, skipped")
    else:
        print("Patching bot.py ...")
        s = sub(s, "\nload_dotenv()\n", "\nimport ratings  # /trending + movie ratings (TMDB / IMDb)\n\nload_dotenv()\n", "import ratings")
        s = sub(
            s,
            '"search", "s", "movie", "request",',
            '"search", "s", "movie", "request", "trending",',
            "/trending is not treated as a movie name",
        )
        s = sub(
            s,
            '    BotCommand("request", "Request a movie: /request name"),\n]',
            '    BotCommand("request", "Request a movie: /request name"),\n'
            '    BotCommand("trending", "Trending movies and series"),\n]',
            "command menu",
        )
        s = sub(
            s,
            '    if AUTO_DELETE_SECONDS > 0:\n        text += f"',
            '    text += ratings.caption_line(title)  # rating of the movie (from the cache)\n'
            '    if AUTO_DELETE_SECONDS > 0:\n        text += f"',
            "rating line in the file caption",
        )
        s = sub(
            s,
            "    caption = file_caption(title, size, lang)\n    kb = file_keyboard(lang)\n",
            "    await ratings.warm(title)  # look the rating up first (cached, waits a few seconds at most)\n"
            "    caption = file_caption(title, size, lang)\n    kb = file_keyboard(lang)\n",
            "rating lookup before sending the file",
        )
        s = sub(s, "async def notify_admins(text: str):\n", HANDLER + "async def notify_admins(text: str):\n", "/trending handler")
        s = sub(
            s,
            '/request <code>name</code>"\n    )\n',
            '/request <code>name</code>\\n"\n        f"\u2022 /trending"\n    )\n',
            "Help page line",
            optional=True,
        )
        s = sub(
            s,
            "    chunk = results[page * RESULTS_PER_PAGE:(page + 1) * RESULTS_PER_PAGE]\n",
            "    chunk = results[page * RESULTS_PER_PAGE:(page + 1) * RESULTS_PER_PAGE]\n"
            "    ratings.prefetch(r[1] for r in chunk)  # warm the rating cache, so the file is sent fast\n",
            "rating prefetch on the result page",
            optional=True,
        )
        try:
            compile(s, "bot.py", "exec")  # never write a broken file
        except SyntaxError as e:
            sys.exit(f"STOP: the patched bot.py has a syntax error ({e}). bot.py was NOT changed.")
        shutil.copyfile("bot.py", "bot.py.bak5")
        with open("bot.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(s)
        print("bot.py: patched (backup: bot.py.bak5)")

    if os.path.exists(".env.example"):
        with open(".env.example", encoding="utf-8") as f:
            env = f.read()
        if "TMDB_API_KEY" not in env:
            with open(".env.example", "a", encoding="utf-8", newline="\n") as f:
                f.write(("" if env.endswith("\n") else "\n") + ENV_BLOCK)
            print(".env.example: TMDB_API_KEY / OMDB_API_KEY added")

    print(
        "\nDone. Next steps:\n"
        "  1. Get the free keys and add them to your hosting variables (Railway -> Variables):\n"
        "       TMDB_API_KEY  (themoviedb.org -> Settings -> API)\n"
        "       OMDB_API_KEY  (omdbapi.com/apikey.aspx)  <- optional, gives the real IMDb rating\n"
        "  2. git add . && git commit -m 'Add /trending and movie ratings' && git push"
    )


if __name__ == "__main__":
    main()
