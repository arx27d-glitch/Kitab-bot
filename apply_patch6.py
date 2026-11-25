"""Kitab-bot patch #6: 3:4 posters + sectioned /trending (Bollywood, Hollywood, South, Other-wood, series, genres ...)
Run inside the repo folder, next to bot.py, moviedb.py and the new trendlists.py:
   python apply_patch6.py            -> apply
   python apply_patch6.py --check    -> only test if every anchor matches, change nothing

Edits: bot.py (backup bot.py.bak6), i18n_extra.py (backup .bak6), requirements.txt, .env.example, railway.env.
Safe: if a required anchor is missing, NOTHING is written and the problems are listed."""
import os
import re
import shutil
import sys

TREND_BLOCK = r'''# ----------------------------------------------------------------------------
# TRENDING: sections (Bollywood / Hollywood / South / Other-wood / series / genres), see trendlists.py
# Tapping a title searches the library.
# ----------------------------------------------------------------------------
TREND_PER_PAGE = 10
TREND_ROWS = [["bm", "hm"], ["sm", "om"], ["bs", "hs"], ["os", "nw"], ["pm", "ps"], ["tm", "ts"]]
TREND_SHORTCUTS = {
    "bollywood": "bm", "hollywood": "hm", "south": "sm", "otherwood": "om",
    "hindiseries": "bs", "englishseries": "hs", "newreleases": "nw",
}


def trend_menu_view(lang: str):
    text = f"✦ <b>{tr(lang, 'trend_title')}</b>\n{LINE}\n♤ {tr(lang, 'trend_pick')}\n{LINE}"
    rows = []
    for pair in TREND_ROWS:
        rows.append(
            [
                btn(
                    f"{trendlists.ICONS[k]} {tr(lang, 'c_' + k)}",
                    BLUE if k in ("bm", "hm") else None,
                    callback_data=f"tl|{k}|0",
                )
                for k in pair
            ]
        )
    rows.append([btn(f"🎭 {tr(lang, 'c_gn')}", GREEN, callback_data="tg")])
    rows.append([InlineKeyboardButton(f"□ {tr(lang, 'b_home')}", callback_data="home")])
    return text, InlineKeyboardMarkup(rows)


def trend_genre_view(lang: str):
    text = f"🎭 <b>{tr(lang, 'c_gn')}</b>\n{LINE}\n♤ {tr(lang, 'trend_pick')}\n{LINE}"
    buttons = [
        InlineKeyboardButton(tr(lang, "g_" + g), callback_data=f"tl|g_{g}|0") for g in trendlists.GENRES
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(f"« {tr(lang, 'b_back')}", callback_data="trend")])
    return text, InlineKeyboardMarkup(rows)


async def trend_list_view(key: str, page: int, lang: str):
    items = await trendlists.get_category(key)
    if not items:
        return None, None
    genre = key.startswith("g_")
    label = f"{tr(lang, 'c_gn')} · {tr(lang, 'g_' + key[2:])}" if genre else tr(lang, "c_" + key)
    icon = "🎭" if genre else trendlists.ICONS[key]
    pages = max(math.ceil(len(items) / TREND_PER_PAGE), 1)
    page = min(max(page, 0), pages - 1)
    start = page * TREND_PER_PAGE
    text = f"{icon} <b>{esc(label)}</b>\n{LINE}\n"
    if key in ("sm", "om", "os"):
        text += f"◇ <i>{tr(lang, 'd_' + key)}</i>\n"
    if pages > 1:
        text += f"□ {tr(lang, 'page')} <b>{page + 1}/{pages}</b>\n"
    text += f"{LINE}\n▼ {tr(lang, 'trend_tap')}"
    rows = []
    for i, it in enumerate(items[start:start + TREND_PER_PAGE], start + 1):
        name = f"{i}. {it['title'][:26]}"
        if it.get("year"):
            name += f" ({it['year']})"
        if it.get("rating"):
            name += f" ★{it['rating']}"
        if key in trendlists.SHOW_LANG and it.get("lang"):
            name += f" [{it['lang'].title()[:8]}]"
        rows.append([InlineKeyboardButton(name[:60], callback_data=f"ts|{it['id']}")])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("«", callback_data=f"tl|{key}|{page - 1}"))
        nav.append(InlineKeyboardButton(f"□ {page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton("»", callback_data=f"tl|{key}|{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"« {tr(lang, 'b_back')}", callback_data="tg" if genre else "trend")])
    return text, InlineKeyboardMarkup(rows)


async def _show_trend_list(key: str, lang: str, send, edit_msg=None):
    """Loads a section (with a 'loading' note on the first load) and shows it."""
    wait = edit_msg
    if not trendlists.is_cached(key) and wait is None:
        wait = await send(f"◇ <b>{tr(lang, 'trend_loading')}</b>", None)
    elif not trendlists.is_cached(key):
        await edit(wait, f"◇ <b>{tr(lang, 'trend_loading')}</b>", None)
    text, kb = await trend_list_view(key, 0, lang)
    if not text:
        text = f"▲ {tr(lang, 'trend_fail')}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"« {tr(lang, 'b_back')}", callback_data="trend")]])
    if wait is not None:
        await edit(wait, text, kb)
        return wait
    return await send(text, kb)


@app.on_message(filters.command(["trending", "popular"]) & user_place)
@safe
async def trending_cmd(client: Client, m: Message):
    if not m.from_user or not await gate(client, m, m.from_user):
        return
    lang = await lang_of(m.from_user)
    text, kb = trend_menu_view(lang)
    reply = await m.reply(text, reply_markup=kb, quote=True)
    schedule_delete(reply, m)


@app.on_message(filters.command(list(TREND_SHORTCUTS)) & user_place)
@safe
async def trend_shortcut_cmd(client: Client, m: Message):
    """/bollywood /hollywood /south /otherwood /hindiseries /englishseries /newreleases"""
    if not m.from_user or not await gate(client, m, m.from_user):
        return
    key = TREND_SHORTCUTS.get(m.command[0].lower().split("@")[0])
    if not key:
        return
    lang = await lang_of(m.from_user)

    async def send(text, kb):
        return await m.reply(text, reply_markup=kb, quote=True)

    reply = await _show_trend_list(key, lang, send)
    schedule_delete(reply, m)


@app.on_callback_query(filters.regex(r"^trend$"))
@safe
async def trend_cb(client: Client, cq: CallbackQuery):
    lang = await lang_of(cq.from_user)
    text, kb = trend_menu_view(lang)
    await edit(cq.message, text, kb)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^tg$"))
@safe
async def trend_genre_cb(client: Client, cq: CallbackQuery):
    lang = await lang_of(cq.from_user)
    text, kb = trend_genre_view(lang)
    await edit(cq.message, text, kb)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^tl\|"))
@safe
async def trend_list_cb(client: Client, cq: CallbackQuery):
    _, key, page = cq.data.split("|")
    if not trendlists.valid(key) or not page.isdigit():
        return await cq.answer()
    lang = await lang_of(cq.from_user)
    await cq.answer()  # the list may need a moment to load
    if not trendlists.is_cached(key):
        await edit(cq.message, f"◇ <b>{tr(lang, 'trend_loading')}</b>", None)
    text, kb = await trend_list_view(key, int(page), lang)
    if not text:
        text = f"▲ {tr(lang, 'trend_fail')}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"« {tr(lang, 'b_back')}", callback_data="trend")]])
    await edit(cq.message, text, kb)


@app.on_callback_query(filters.regex(r"^ts\|"))
@safe
async def trend_search_cb(client: Client, cq: CallbackQuery):
    lang = await lang_of(cq.from_user)
    item_id = cq.data.split("|", 1)[1]
    item = trendlists.find_item(item_id) or moviedb.find_trending(item_id)
    if not item:
        return await cq.answer(tr(lang, "a_expired"), show_alert=True)
    await cq.answer()
    await search_from_callback(client, cq, item["title"])


'''

POSTER_FUNC = r'''async def reply_with_poster(target: Message, poster: str, text: str, kb, quote: bool = True):
    """Replies with the poster (cut to 3:4) and the text as its caption. If the poster can't be sent: only the text."""
    if poster and plain_len(text) <= 1024:
        for attempt in (0, 1):
            try:
                # attempt 0: our own 3:4 picture (trendlists.poster_34). attempt 1: the plain url as a fallback
                photo = await trendlists.poster_34(poster) if attempt == 0 else poster
                if not photo:
                    continue
                return await target.reply_photo(photo, caption=text, reply_markup=kb, quote=quote)
            except FloodWait:
                raise
            except Exception as e:
                log.info("Poster not sent (attempt %s): %s", attempt + 1, e)
    return await target.reply(text, reply_markup=kb, quote=quote, link_preview_options=NO_PREVIEW)'''

I18N_BLOCK = '''

# ---- patch #6: trending sections (English + Hindi; other languages fall back to English)
T["en"].update(
    dict(
        trend_loading="Loading the list, please wait a few seconds...",
        c_bm="Bollywood Top 10", c_hm="Hollywood Top 10", c_sm="South Indian Movies",
        c_om="Other-wood Movies", c_bs="Hindi / Indian Series", c_hs="English Series",
        c_os="Other Series", c_nw="New Releases", c_pm="Popular Movies", c_ps="Popular Series",
        c_tm="Top Rated Movies", c_ts="Top Rated Series", c_gn="Genres",
        d_sm="Tollywood, Kollywood, Mollywood, Sandalwood (Telugu, Tamil, Malayalam, Kannada)",
        d_om="Korean, Japanese, Turkish, Punjabi, Bengali and other world cinema",
        d_os="K-Drama, Anime, Turkish, South Indian and other series",
        g_Action="Action", g_Comedy="Comedy", g_Horror="Horror", g_Thriller="Thriller", g_Romance="Romance",
        **{"g_Sci-Fi": "Sci-Fi"},
        g_Animation="Animation", g_Crime="Crime", g_Drama="Drama", g_Adventure="Adventure",
        g_Fantasy="Fantasy", g_Mystery="Mystery", g_Family="Family", g_War="War",
        g_Biography="Biography", g_Documentary="Documentary",
        help_cmds=(
            "/search name - search a file\\n"
            "/info name - poster, rating, plot and cast\\n"
            "/trending - Bollywood, Hollywood, South, series, genres ...\\n"
            "/bollywood /hollywood /south /otherwood - top 10 lists\\n"
            "/hindiseries /englishseries /newreleases - more lists\\n"
            "/request name - ask for a movie we don't have\\n"
            "/myplan - your plan and today's downloads\\n"
            "/language - change the language"
        ),
    )
)

T["hi"].update(
    dict(
        trend_loading="लिस्ट लोड हो रही है, कुछ सेकंड रुकिए...",
        c_bm="बॉलीवुड टॉप 10", c_hm="हॉलीवुड टॉप 10", c_sm="साउथ इंडियन मूवीज़",
        c_om="अदर-वुड मूवीज़", c_bs="हिंदी / इंडियन सीरीज़", c_hs="इंग्लिश सीरीज़",
        c_os="दूसरी सीरीज़", c_nw="नई रिलीज़", c_pm="पॉपुलर मूवीज़", c_ps="पॉपुलर सीरीज़",
        c_tm="टॉप रेटेड मूवीज़", c_ts="टॉप रेटेड सीरीज़", c_gn="जॉनर",
        d_sm="टॉलीवुड, कॉलीवुड, मॉलीवुड, सैंडलवुड (तेलुगु, तमिल, मलयालम, कन्नड़)",
        d_om="कोरियन, जापानी, तुर्की, पंजाबी, बंगाली और दूसरी वर्ल्ड सिनेमा",
        d_os="के-ड्रामा, एनीमे, तुर्की, साउथ और दूसरी सीरीज़",
        g_Action="एक्शन", g_Comedy="कॉमेडी", g_Horror="हॉरर", g_Thriller="थ्रिलर", g_Romance="रोमांस",
        **{"g_Sci-Fi": "साई-फाई"},
        g_Animation="एनिमेशन", g_Crime="क्राइम", g_Drama="ड्रामा", g_Adventure="एडवेंचर",
        g_Fantasy="फैंटेसी", g_Mystery="मिस्ट्री", g_Family="फैमिली", g_War="वॉर",
        g_Biography="बायोपिक", g_Documentary="डॉक्यूमेंट्री",
        help_cmds=(
            "/search नाम - फ़ाइल खोजें\\n"
            "/info नाम - पोस्टर, रेटिंग, कहानी और कास्ट\\n"
            "/trending - बॉलीवुड, हॉलीवुड, साउथ, सीरीज़, जॉनर ...\\n"
            "/bollywood /hollywood /south /otherwood - टॉप 10 लिस्ट\\n"
            "/hindiseries /englishseries /newreleases - और लिस्ट\\n"
            "/request नाम - जो मूवी हमारे पास नहीं है उसकी माँग करें\\n"
            "/myplan - आपका प्लान और आज के डाउनलोड\\n"
            "/language - भाषा बदलें"
        ),
    )
)
'''

ENV_EXAMPLE = """
# ===== Trending sections (optional) =====
# How many popular titles are scanned to find Bollywood / Hollywood / South / other-wood titles.
# Bigger = more results in each list, but the first load is slower.
TREND_DEPTH_MOVIE=400
TREND_DEPTH_SERIES=200
# How long a list is remembered (minutes)
TREND_CACHE_MIN=360
"""
ENV_RAILWAY = "TREND_DEPTH_MOVIE=400\nTREND_DEPTH_SERIES=200\nTREND_CACHE_MIN=360\n"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    if os.path.exists(p):
        shutil.copyfile(p, p + ".bak6")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


class Patch:
    def __init__(self, text):
        self.s, self.errors, self.warns = text, [], []

    def sub(self, old, new, label, required=True):
        n = self.s.count(old)
        if n == 1:
            self.s = self.s.replace(old, new, 1)
        else:
            (self.errors if required else self.warns).append(f"{label} (found {n} times, need exactly 1)")

    def rx(self, pattern, new, label, required=True):
        self.s, n = re.subn(pattern, lambda m: new, self.s, count=1, flags=re.S)
        if n != 1:
            (self.errors if required else self.warns).append(f"{label} (not found)")


def build_bot():
    s = read("bot.py")
    if "import trendlists" in s:
        return None, [], []
    p = Patch(s)
    p.sub("import moviedb\n", "import moviedb\nimport trendlists  # 3:4 posters + trending sections\n", "import moviedb")
    p.rx(r"async def reply_with_poster\(.*?(?=\n\n\nasync def send_info_card)", POSTER_FUNC, "reply_with_poster")
    p.rx(r"# -+\n# TRENDING:[^\n]*\n# -+\n.*?(?=# -+\n# SEARCH\n)", TREND_BLOCK, "TRENDING section")
    p.sub('"info", "trending", "popular", "request",',
          '"info", "trending", "popular", "bollywood", "hollywood", "south", "otherwood", "hindiseries", '
          '"englishseries", "newreleases", "request",', "search_handler exclusion list")
    p.sub('        BotCommand("trending", "Popular movies and series"),\n',
          '        BotCommand("trending", "Bollywood, Hollywood, South, series ..."),\n'
          '        BotCommand("bollywood", "Bollywood top 10"),\n'
          '        BotCommand("hollywood", "Hollywood top 10"),\n'
          '        BotCommand("south", "South Indian top 10"),\n', "menu commands", required=False)
    p.sub("    await set_menu_commands()\n    if AUTO_INDEX_ON_START:",
          "    await set_menu_commands()\n    asyncio.create_task(trendlists.warm())  # load the trending lists in the background\n"
          "    if AUTO_INDEX_ON_START:", "startup warm-up", required=False)
    return p.s, p.errors, p.warns


def main():
    check_only = "--check" in sys.argv
    for need in ("bot.py", "moviedb.py", "i18n_extra.py", "trendlists.py"):
        if not os.path.exists(need):
            sys.exit(f"{need} not found. Run this script inside the Kitab-bot folder (trendlists.py must be there too).")
    bot, errors, warns = build_bot()
    if errors:
        print("NOTHING was changed. These anchors did not match:")
        for e in errors:
            print("  x", e)
        sys.exit(1)
    if bot is not None:
        try:
            compile(bot, "bot.py", "exec")
        except SyntaxError as e:
            sys.exit(f"STOP: the patched bot.py would have a syntax error ({e}). Nothing was changed.")
    for w in warns:
        print("  (optional part skipped)", w)
    if check_only:
        print("OK: every required anchor matches. Run again without --check to apply.")
        return

    if bot is None:
        print("bot.py: already patched, skipped")
    else:
        write("bot.py", bot)
        print("bot.py: patched (backup: bot.py.bak6)")

    extra = read("i18n_extra.py")
    if "trend_loading" not in extra:
        write("i18n_extra.py", extra.rstrip("\n") + "\n" + I18N_BLOCK)
        print("i18n_extra.py: trending texts added")

    if os.path.exists("requirements.txt"):
        req = read("requirements.txt")
        if "pillow" not in req.lower():
            write("requirements.txt", req.rstrip("\n") + "\nPillow>=10.0.0\n")
            print("requirements.txt: Pillow added (needed for the 3:4 poster)")
    for path, add in ((".env.example", ENV_EXAMPLE), ("railway.env", ENV_RAILWAY)):
        if os.path.exists(path):
            text = read(path)
            if "TREND_DEPTH_MOVIE" not in text:
                write(path, text.rstrip("\n") + "\n" + add)
                print(path + ": updated")
    print("\nDone. Now: git add . && git commit -m 'Trending sections + 3:4 posters' && git push")


if __name__ == "__main__":
    main()
