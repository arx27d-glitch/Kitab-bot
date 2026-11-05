import asyncio
import html
import logging
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pyrogram import Client, enums, filters, idle
from pyrogram.errors import (
    FloodWait,
    InputUserDeactivated,
    MessageNotModified,
    PeerIdInvalid,
    RPCError,
    UserIsBlocked,
    UserNotParticipant,
)
from pyrogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from i18n import LANGS, detect_lang, tr
from quality import LANG_NAMES, LANG_ORDER, ORDER as QUALITY_ORDER, detect_languages, detect_quality, detect_seasons
from translit import phonetic_key, phonetic_words, to_latin
from storage import MongoStore, MultiMongoStore, SqliteStore

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bookbot")
START_TIME = time.time()


# ----------------------------------------------------------------------------
# CONFIG (everything comes from environment variables, see .env.example)
# ----------------------------------------------------------------------------
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: str) -> bool:
    return env(name, default).lower() in ("1", "true", "yes")


API_ID = int(env("API_ID", "0"))
API_HASH = env("API_HASH")
BOT_TOKEN = env("BOT_TOKEN")
DB_CHANNEL = int(env("DB_CHANNEL", "0"))
ADMINS = [int(x) for x in env("ADMINS").replace(",", " ").split() if x.lstrip("-").isdigit()]
# env wale ADMINS = owners. /addadmin se jude admin bhi yahan aa jate hain.
ALL_ADMINS = set(ADMINS)

# Database: provide MONGO_URI so data survives restarts (recommended)
def load_mongo_uris():
    """MONGO_URI, MONGO_URI_1 ... MONGO_URI_10: any number from 1 to 10 works (gaps are fine)."""
    keys = ["MONGO_URI"] + [f"MONGO_URI_{i}" for i in range(1, 11)]
    uris = []
    for key in keys:
        value = env(key)
        if value and value not in uris:
            uris.append(value)
    return uris[:10]


MONGO_URIS = load_mongo_uris()
MONGO_LIMIT_MB = int(env("MONGO_LIMIT_MB", "450") or 450)  # a database is "full" at this size
MONGO_DB_NAME = env("MONGO_DB_NAME", "bookbot")
DB_PATH = env("DB_PATH", "files.db")  # only used when MONGO_URI is not set

# Auto-forward: new messages/files from these groups are copied to DB_CHANNEL automatically
SOURCE_GROUPS = [int(x) for x in env("SOURCE_GROUPS").replace(",", " ").split() if x.lstrip("-").isdigit()]
FORWARD_ALL = env_bool("FORWARD_ALL", "false")  # true = forward text messages too

# Files in the DB channel get indexed as soon as the bot starts
AUTO_INDEX_ON_START = env_bool("AUTO_INDEX_ON_START", "true")
# If the bot can't post in the DB channel, give the last message id here for scanning
DB_LAST_MESSAGE_ID = int(env("DB_LAST_MESSAGE_ID", "0") or 0)

BOT_NAME = env("BOT_NAME", "MOVIE HUB ☆ Bot")
OWNER_USERNAME = env("OWNER_USERNAME").lstrip("@")
SUPPORT_USERNAME = env("SUPPORT_USERNAME").lstrip("@")
UPDATES_CHANNEL = env("UPDATES_CHANNEL").lstrip("@")
START_PIC = env("START_PIC")  # optional default welcome photo (admin can override with /setstart)

AUTO_DELETE_SECONDS = int(env("AUTO_DELETE_SECONDS", "300"))  # 300 = 5 minutes, 0 = off
RESULTS_PER_PAGE = int(env("RESULTS_PER_PAGE", "8"))

# Optional: custom text. You can use {mention} {first_name} {bot_name} {minutes}
START_TEXT_ENV = env("START_TEXT").replace("\\n", "\n")
JOIN_TEXT_ENV = env("JOIN_TEXT").replace("\\n", "\n")


def parse_chat(value):
    value = str(value).strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value.lstrip("@")


def load_force_channels():
    """Reads CHANNEL_1 ... CHANNEL_10.

    CHANNEL_n      = @username or -100xxxxxxxxxx (numeric id)
    CHANNEL_n_LINK = invite link (required for private channels, optional for public ones)
    """
    channels = []
    for i in range(1, 11):
        raw = env(f"CHANNEL_{i}")
        if not raw:
            continue
        ref = parse_chat(raw)
        link = env(f"CHANNEL_{i}_LINK")
        if not link and isinstance(ref, str):
            link = f"https://t.me/{ref}"
        if not link:
            log.warning("CHANNEL_%s is private, please also set CHANNEL_%s_LINK.", i, i)
        channels.append({"n": i, "ref": ref, "link": link})
    return channels


ENV_CHANNELS = load_force_channels()

# Group where a notification is sent whenever someone starts the bot.
# LOG_GROUP not set -> the first SOURCE_GROUPS group is used.
_log_raw = env("LOG_GROUP")
LOG_GROUP = parse_chat(_log_raw) if _log_raw else (SOURCE_GROUPS[0] if SOURCE_GROUPS else 0)

# Auto-reply group: user messages are mirrored here, movie requests (not available) and
# "file sent to user" cards go here, and admins can answer users with /sent.
# AUTO_REPLY_GROUP not set -> same group as LOG_GROUP.
_auto_raw = env("AUTO_REPLY_GROUP")
AUTO_GROUP = parse_chat(_auto_raw) if _auto_raw else LOG_GROUP
# false = messages of admins/owners are not mirrored (true is handy while testing with your own account)
MIRROR_ADMINS = env_bool("MIRROR_ADMIN_MESSAGES", "false")

# Groups where ALL users can use the bot's commands (/start /help /language /search):
# SOURCE_GROUPS + LOG_GROUP + AUTO_REPLY_GROUP + the groups listed in USER_GROUPS.
# Owner/admin commands work in private chat and in LOG_GROUP / AUTO_REPLY_GROUP only.
USER_GROUPS = [parse_chat(x) for x in env("USER_GROUPS").replace(",", " ").split()]
# true = a normal text message in those groups is also searched (needs privacy mode OFF in BotFather)
GROUP_TEXT_SEARCH = env_bool("GROUP_TEXT_SEARCH", "false")

if not (API_ID and API_HASH and BOT_TOKEN and DB_CHANNEL):
    raise SystemExit("API_ID, API_HASH, BOT_TOKEN and DB_CHANNEL are required (see .env).")

app = Client(
    "bookbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    parse_mode=enums.ParseMode.HTML,
)
BOT_USERNAME = ""

if len(MONGO_URIS) > 1:
    store = MultiMongoStore(MONGO_URIS, MONGO_DB_NAME, MONGO_LIMIT_MB)
elif MONGO_URIS:
    store = MongoStore(MONGO_URIS[0], MONGO_DB_NAME)
else:
    store = SqliteStore(DB_PATH)
    log.warning(
        "MONGO_URI is not set, using SQLite. On Heroku/Railway/Render the data may be lost after a "
        "restart. Provide MONGO_URI for permanent data."
    )


# ----------------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------------
LINE = "━━━━━━━━━━━━━━━━━━"

# Link preview off (new-style option, replaces disable_web_page_preview)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# Colored buttons (Bot API 9.4+). Needs PyroTGFork (see requirements.txt)
_BS = getattr(enums, "ButtonStyle", None)
BLUE = _BS.PRIMARY if _BS else None
GREEN = _BS.SUCCESS if _BS else None
RED = _BS.DANGER if _BS else None


def btn(text: str, style=None, **kw) -> InlineKeyboardButton:
    """InlineKeyboardButton with optional color. Falls back to a normal button if unsupported."""
    if style is not None:
        try:
            return InlineKeyboardButton(text, style=style, **kw)
        except TypeError:
            log.warning("This pyrogram version has no button colors, using normal button.")
    return InlineKeyboardButton(text, **kw)


def esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


def norm(text: str) -> str:
    return re.sub(r"[._\-\[\]\(\)]+", " ", text or "").lower().strip()


def human(size) -> str:
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def file_icon(title: str) -> str:
    t = (title or "").lower()
    if t.endswith(".pdf"):
        return "♡"
    if t.endswith((".epub", ".mobi", ".azw3")):
        return "♧"
    if t.endswith((".doc", ".docx", ".odt")):
        return "◇"
    if t.endswith((".ppt", ".pptx")):
        return "♤"
    if t.endswith((".txt", ".rtf")):
        return "□"
    if t.endswith((".zip", ".rar", ".7z")):
        return "¤"
    if t.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
        return "☆"
    if t.endswith((".mp3", ".m4a", ".ogg", ".wav", ".flac")):
        return "♪"
    return "☆"


def progress_bar(done: int, total: int, width: int = 8) -> str:
    total = max(total, 1)
    filled = round(width * done / total)
    return "▰" * filled + "▱" * (width - filled)


def fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h or d:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def minutes() -> int:
    return max(AUTO_DELETE_SECONDS // 60, 1)


# ----------------------------------------------------------------------------
# ADMINS (env owners + admins added with /addadmin)
# ----------------------------------------------------------------------------
def is_admin_id(user_id: int) -> bool:
    return user_id in ALL_ADMINS


async def _admin_check(_, __, m):
    return bool(getattr(m, "from_user", None)) and m.from_user.id in ALL_ADMINS


# live filter: /addadmin ke turant baad naya admin commands chala sakta hai
admin_filter = filters.create(_admin_check)

# sirf env wale owners (/addadmin, /deladmin ke liye)
owner_filter = filters.user(ADMINS)

# Group ids (usernames are turned into ids when the bot starts, see resolve_groups)
ADMIN_GROUPS = {g for g in (LOG_GROUP, AUTO_GROUP) if isinstance(g, int) and g}
USER_GROUP_IDS = (
    set(ADMIN_GROUPS)
    | {g for g in SOURCE_GROUPS if isinstance(g, int)}
    | {g for g in USER_GROUPS if isinstance(g, int)}
)


async def _in_admin_groups(_, __, m):
    return bool(getattr(m, "chat", None)) and m.chat.id in ADMIN_GROUPS


async def _in_user_groups(_, __, m):
    return bool(getattr(m, "chat", None)) and m.chat.id in USER_GROUP_IDS


async def _in_search_groups(_, __, m):  # plain-text search: user groups, but never the log group
    return bool(getattr(m, "chat", None)) and m.chat.id in USER_GROUP_IDS and m.chat.id not in ADMIN_GROUPS


# admin_place: private chat + log/auto-reply group      user_place: private chat + my groups
admin_place = filters.private | filters.create(_in_admin_groups)
user_place = filters.private | filters.create(_in_user_groups)


async def resolve_groups():
    """Turns @usernames of groups into ids and fills the group lists."""
    global LOG_GROUP, AUTO_GROUP

    async def to_id(ref):
        if not ref or isinstance(ref, int):
            return ref
        try:
            return (await app.get_chat(ref)).id
        except Exception as e:
            log.warning("Could not find group %s (%s). Is the bot a member?", ref, e)
            return ref

    LOG_GROUP = await to_id(LOG_GROUP)
    AUTO_GROUP = await to_id(AUTO_GROUP)
    ADMIN_GROUPS.clear()
    ADMIN_GROUPS.update(g for g in (LOG_GROUP, AUTO_GROUP) if isinstance(g, int) and g)
    USER_GROUP_IDS.clear()
    USER_GROUP_IDS.update(ADMIN_GROUPS)
    for ref in list(SOURCE_GROUPS) + list(USER_GROUPS):
        gid = await to_id(ref)
        if isinstance(gid, int):
            USER_GROUP_IDS.add(gid)


async def load_admins():
    raw = await store.get_meta("extra_admins", "")
    ALL_ADMINS.update(int(x) for x in raw.split() if x.lstrip("-").isdigit())


async def save_admins():
    extra = sorted(ALL_ADMINS - set(ADMINS))
    await store.set_meta("extra_admins", " ".join(map(str, extra)))


_known_users = set()


async def register_user(user_id: int) -> bool:
    """Saves the user. Returns True if this user is new."""
    is_new = user_id not in _known_users
    await store.add_user(user_id)
    _known_users.add(user_id)
    return is_new


async def log_start(client: Client, user, is_new: bool):
    """Sends a 'user started the bot' card to LOG_GROUP."""
    if not LOG_GROUP:
        return
    ist = timezone(timedelta(hours=5, minutes=30))
    when = datetime.now(ist).strftime("%d %b %Y, %I:%M %p IST")
    text = (
        ("♡ <b>New User Started The Bot</b>\n" if is_new else "♧ <b>User Started The Bot</b>\n")
        + LINE
        + f"\n♧ Name: {user.mention}\n"
        f"¤ ID: <code>{user.id}</code>\n"
        f"◇ Username: {('@' + esc(user.username)) if user.username else 'none'}\n"
        f"□ Time: {when}\n"
        f"☆ Total users: <b>{await store.count_users()}</b>\n"
        + LINE
    )
    group_text(LOG_GROUP, text)


# ---- everything that goes to the groups is sent through one queue (in order, flood-safe)
_log_queue = None


async def _log_worker():
    while True:
        fn = await _log_queue.get()
        try:
            try:
                await fn()
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                await fn()
        except Exception as e:
            log.warning("Could not send to the group (%s). Is the bot added there?", e)
        await asyncio.sleep(0.4)


def enqueue_group(fn):
    """fn = a function without arguments that returns the coroutine to run."""
    if _log_queue is None:
        return
    try:
        _log_queue.put_nowait(fn)
    except asyncio.QueueFull:
        log.warning("Group queue is full, dropping a message")


def group_text(chat, text: str):
    if chat:
        enqueue_group(lambda: app.send_message(chat, text, link_preview_options=NO_PREVIEW))


def now_ist() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%d %b %Y, %I:%M %p IST")


def user_tag(user) -> str:
    uname = f"@{esc(user.username)}" if user.username else "no username"
    return f"♧ {user.mention} ┃ {uname}\n¤ ID: <code>{user.id}</code>"


_NO_CAPTION_TYPES = ("sticker", "video_note", "contact", "location", "venue", "poll", "dice", "game")


def mirror_user_message(m: Message):
    """Copies a message of a user into the auto-reply group (with the user's name + id on top)."""
    if not AUTO_GROUP:
        return
    head = user_tag(m.from_user)
    if m.text:
        body = f"{head}\n{LINE}\n{esc(m.text)[:3500]}"
        enqueue_group(lambda: app.send_message(AUTO_GROUP, body, link_preview_options=NO_PREVIEW))
        return
    kind = str(m.media.name).lower().replace("_", " ") if m.media else "message"
    if any(getattr(m, t, None) for t in _NO_CAPTION_TYPES):
        note = f"{head}\n{LINE}\n◇ sent a <b>{kind}</b>"
        enqueue_group(lambda: app.send_message(AUTO_GROUP, note, link_preview_options=NO_PREVIEW))
        enqueue_group(lambda: m.copy(AUTO_GROUP))
        return
    cap = esc(m.caption)[:700] if m.caption else ""
    caption = f"{head}\n{LINE}\n◇ <b>{kind}</b>" + (f"\n{cap}" if cap else "")
    enqueue_group(lambda: m.copy(AUTO_GROUP, caption=caption))


_req_seen: dict = {}


def log_movie_request(user, query: str):
    """Movie not found -> card in the auto-reply group (same user + same name only once per 10 min)."""
    if not AUTO_GROUP:
        return
    key = (user.id, norm(query))
    now = time.time()
    if now - _req_seen.get(key, 0) < 600:
        return
    _req_seen[key] = now
    if len(_req_seen) > 3000:
        for k in sorted(_req_seen, key=_req_seen.get)[:1500]:
            _req_seen.pop(k, None)
    group_text(
        AUTO_GROUP,
        "☆ <b>Movie Request</b> ┃ ✗ <b>Not Available</b>\n"
        + LINE
        + f"\n{user_tag(user)}\n"
        f"□ Requested: <i>{esc(query[:100])}</i>\n"
        f"◇ Time: {now_ist()}\n"
        + LINE
        + "\n♤ <i>Reply to this message with</i> <code>/sent your text</code> "
        "<i>(or send a file with the caption</i> <code>/sent</code><i>) to answer this user.</i>",
    )


def log_file_sent(user, title: str, size: int):
    if not AUTO_GROUP:
        return
    group_text(
        AUTO_GROUP,
        "✓ <b>File Sent To This User</b>\n"
        + LINE
        + f"\n{user_tag(user)}\n"
        f"{file_icon(title)} <b>{esc(title[:150])}</b>\n"
        f"□ Size: <b>{human(size)}</b>\n"
        f"◇ Time: {now_ist()}",
    )


_tasks = set()


def schedule_delete(*messages: Message, delay: int = None):
    """Deletes the messages after `delay` seconds (auto-delete)."""
    delay = AUTO_DELETE_SECONDS if delay is None else delay
    if delay <= 0:
        return

    async def _job():
        await asyncio.sleep(delay)
        for msg in messages:
            try:
                await msg.delete()
            except Exception:
                pass

    task = asyncio.create_task(_job())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def plain_len(text: str) -> int:
    return len(re.sub(r"<[^>]+>", "", text or ""))


async def edit(msg: Message, text: str, kb=None):
    """Edits a text message or a photo caption.

    A photo caption can only be 1024 characters long. When the new text is longer (for example
    the Help page of an admin) the photo message is replaced by a normal text message.
    """
    has_media = bool(msg.photo or msg.video or msg.animation or msg.document)
    try:
        if has_media and plain_len(text) > 1024:
            await msg.reply(text, reply_markup=kb, quote=False, link_preview_options=NO_PREVIEW)
            try:
                await msg.delete()
            except Exception:
                pass
        elif has_media:
            await msg.edit_caption(text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb, link_preview_options=NO_PREVIEW)
    except MessageNotModified:
        pass
    except Exception as e:
        log.warning("Could not edit the message (%s), sending a new one", e)
        try:
            await msg.reply(text, reply_markup=kb, quote=False, link_preview_options=NO_PREVIEW)
        except Exception as e2:
            log.error("Could not send the message either: %s", e2)


# ----------------------------------------------------------------------------
# LANGUAGE: every user has his own language (chosen on /start, changeable with /language)
# ----------------------------------------------------------------------------
_user_lang: dict = {}


async def lang_of(user) -> str:
    """Language of a user: his choice -> his Telegram language -> English."""
    lg = _user_lang.get(user.id)
    if lg:
        return lg
    saved = await store.get_meta(f"lang:{user.id}", "")
    lg = saved if saved in LANGS else detect_lang(getattr(user, "language_code", None))
    if len(_user_lang) > 5000:
        _user_lang.clear()
    _user_lang[user.id] = lg
    return lg


async def has_chosen_lang(user_id: int) -> bool:
    return (await store.get_meta(f"lang:{user_id}", "")) in LANGS


async def set_lang(user_id: int, code: str):
    await store.set_meta(f"lang:{user_id}", code)
    _user_lang[user_id] = code


def lang_pick_text() -> str:
    return (
        "◇ <b>Choose your language</b>\n"
        f"◇ <b>{tr('hi', 'lang_title')}</b>\n"
        f"◇ <b>{tr('ar', 'lang_title')}</b>\n"
        f"◇ <b>{tr('ru', 'lang_title')}</b>"
    )


def lang_keyboard():
    items = list(LANGS.items())
    rows = []
    for i in range(0, len(items), 2):
        rows.append(
            [
                InlineKeyboardButton(f"{flag} {name}", callback_data=f"lg|{code}")
                for code, (name, flag) in items[i:i + 2]
            ]
        )
    return InlineKeyboardMarkup(rows)


# ----------------------------------------------------------------------------
# UI: texts + buttons
# ----------------------------------------------------------------------------
def welcome_text(user, lang: str = "en") -> str:
    if START_TEXT_ENV:  # a custom text from .env is used for every language
        return START_TEXT_ENV.format(
            mention=user.mention,
            first_name=esc(user.first_name),
            bot_name=esc(BOT_NAME),
            minutes=minutes(),
        )
    return (
        f"◇ <b>{esc(BOT_NAME)}</b> ◇\n"
        + LINE
        + f"\n♡ {tr(lang, 'hello', mention=user.mention)}\n\n"
        f"☆ {tr(lang, 'send_name')}\n\n"
        f"┏ ¤ <b>{tr(lang, 'f_search')}</b>\n"
        f"┣ □ <b>{tr(lang, 'f_delivery')}</b>\n"
        f"┗ ◇ {tr(lang, 'f_autodel', minutes=minutes())}\n"
        + LINE
        + f"\n♤ <i>{tr(lang, 'tip')}</i> <code>Coolie </code>"
    )


def help_text(is_admin: bool, is_owner: bool = False, lang: str = "en") -> str:
    text = (
        f"☆ <b>{tr(lang, 'how_title')}</b>\n"
        + LINE
        + f"\n1. {tr(lang, 'step1')}\n"
        f"2. {tr(lang, 'step2')}\n"
        f"3. {tr(lang, 'step3', minutes=minutes())}\n"
        + LINE
        + f"\n♤ <b>{tr(lang, 'tips_title')}</b>\n"
        f"• {tr(lang, 'tip1')}\n"
        f"• {tr(lang, 'tip2')}\n"
        f"• {tr(lang, 'tip3')}\n"
        f"• {tr(lang, 'tip4')} <code>KGF </code>"
    )
    if is_admin:  # admin / owner commands stay in English
        text += (
            "\n\n♛ <b>Admin Commands</b>\n"
            + LINE
            + "\n/stats - bot statistics\n"
            "/broadcast - message everyone (reply to a message or add text)\n"
            "/index - index new files (<code>/index full</code> = full scan)\n"
            "/addchannel - add a force-join channel\n"
            "/delchannel - remove a channel\n"
            "/channels - list channels and their status\n"
            "/setstart - set the start image (send a photo with caption or reply to a photo)\n"
            "/delstart - remove the start image\n"
            "/admins - list admins\n"
            "/sent - send a message/file to a user (<code>/sent user_id text</code>, or reply to a file)"
        )
    if is_owner:
        text += (
            "\n\n♔ <b>Owner Commands</b>\n"
            + LINE
            + "\n/addadmin - add an admin\n"
            "/deladmin - remove an admin\n"
            "/del - delete a file from the database (<code>/del name</code> or <code>/del id</code>)\n"
            "/dbset - set the database channel (<code>/dbset -100...</code>)"
        )
    return text


async def about_text(lang: str = "en") -> str:
    files = await store.count_files()
    users = await store.count_users()
    text = (
        f"¤ <b>{esc(BOT_NAME)}</b> ┃ {tr(lang, 'about_title')}\n"
        + LINE
        + f"\n☆ {tr(lang, 'files')}: <b>{files}</b>\n"
        f"♧ {tr(lang, 'users')}: <b>{users}</b>\n"
        f"◇ {tr(lang, 'f_autodel', minutes=minutes())}\n"
    )
    if BOT_USERNAME:
        text += f"♧ Bot: @{BOT_USERNAME}\n"
    if OWNER_USERNAME:
        text += f"♡ {tr(lang, 'b_owner')}: @{esc(OWNER_USERNAME)}\n"
    text += LINE + f"\n♡ <i>{tr(lang, 'motto')}</i>"
    return text


def link_buttons(lang: str = "en"):
    row = []
    if UPDATES_CHANNEL:
        row.append(InlineKeyboardButton(f"◇ {tr(lang, 'b_updates')}", url=f"https://t.me/{UPDATES_CHANNEL}"))
    if SUPPORT_USERNAME:
        row.append(btn(f"♡ {tr(lang, 'b_support')}", BLUE, url=f"https://t.me/{SUPPORT_USERNAME}"))
    return row


def home_keyboard(lang: str = "en"):
    rows = [
        [
            btn(f"☆ {tr(lang, 'b_help')}", BLUE, callback_data="help"),
            btn(f"¤ {tr(lang, 'b_about')}", GREEN, callback_data="about"),
        ]
    ]
    links = link_buttons(lang)
    if links:
        rows.append(links)
    if OWNER_USERNAME:
        rows.append([btn(f"♤ {tr(lang, 'b_owner')}", GREEN, url=f"https://t.me/{OWNER_USERNAME}")])
    rows.append([InlineKeyboardButton(f"◇ {tr(lang, 'b_lang')}", callback_data="lang")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(lang: str = "en"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"□ {tr(lang, 'b_home')}", callback_data="home")]])


def file_keyboard(lang: str = "en"):
    row = link_buttons(lang)
    if OWNER_USERNAME:
        row.append(btn(f"♤ {tr(lang, 'b_owner')}", GREEN, url=f"https://t.me/{OWNER_USERNAME}"))
    return InlineKeyboardMarkup([row]) if row else None


async def send_welcome(client: Client, chat_id: int, user, lang: str = "en"):
    text = welcome_text(user, lang)
    kb = home_keyboard(lang)
    pic = await store.get_meta("start_pic", "") or START_PIC
    if pic:
        try:
            return await client.send_photo(chat_id, pic, caption=text, reply_markup=kb)
        except Exception as e:
            log.warning("Could not send start pic (%s), sending text instead", e)
    return await client.send_message(chat_id, text, reply_markup=kb, link_preview_options=NO_PREVIEW)


# ----------------------------------------------------------------------------
# FORCE JOIN
# ----------------------------------------------------------------------------
async def get_force_channels():
    """Env channels + channels added via /addchannel (merged by slot number)."""
    merged = {c["n"]: c for c in ENV_CHANNELS}
    for slot, ref, link in await store.get_channels():
        if not ref:  # slot removed via /delchannel
            merged.pop(slot, None)
            continue
        merged[slot] = {"n": slot, "ref": parse_chat(ref), "link": link}
    return [merged[k] for k in sorted(merged)]


async def not_joined(client: Client, user_id: int):
    missing = []
    for ch in await get_force_channels():
        try:
            member = await client.get_chat_member(ch["ref"], user_id)
            if member.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
                missing.append(ch)
        except UserNotParticipant:
            missing.append(ch)
        except RPCError as e:
            # Bot is not admin in the channel or the channel is wrong: don't block the user
            log.error("Could not check channel %s (%s). Make the bot an admin there.", ch["ref"], e)
    return missing


async def join_view(missing, lang: str = "en"):
    """(text, keyboard) - join screen with progress."""
    total = len(await get_force_channels())
    joined = max(total - len(missing), 0)
    if JOIN_TEXT_ENV:  # a custom text from .env is used for every language
        text = JOIN_TEXT_ENV
    else:
        text = (
            f"□ <b>{tr(lang, 'locked')}</b>\n"
            + LINE
            + f"\n{tr(lang, 'join_msg', n=len(missing))}\n\n"
            f"□ {tr(lang, 'progress')}: {progress_bar(joined, total)} <b>{joined}/{total}</b>\n"
            + LINE
            + f"\n{tr(lang, 'after_join')}"
        )
    rows = []
    for ch in missing:
        if ch["link"]:
            rows.append([InlineKeyboardButton(f"◇ {tr(lang, 'b_join')} {ch['n']}  ↗", url=ch["link"])])
    rows.append([InlineKeyboardButton(f"✓ {tr(lang, 'b_joined')}", callback_data="recheck")])
    return text, InlineKeyboardMarkup(rows)


# ----------------------------------------------------------------------------
# INDEXING (file name + file_id are saved in the database)
# ----------------------------------------------------------------------------
def search_text(title: str, caption: str) -> str:
    """Text used for searching: the name + the same name in Latin letters (for Hindi/Tamil... names)."""
    raw = f"{title} {caption}"
    text = norm(raw)
    latin = to_latin(raw)
    if latin != raw:
        text += " " + norm(latin)
    return text


async def index_message(m: Message) -> bool:
    media = m.document or m.video or m.audio
    if not media:
        return False
    caption = m.caption or ""
    title = getattr(media, "file_name", None) or caption or f"file_{m.id}"
    await store.upsert_file(
        m.id, title, search_text(title, caption), media.file_size or 0, media.file_id, caption
    )
    log.info("Indexed: %s", title)
    return True


# Any new file posted in the DB channel is indexed automatically
async def _in_db_channel(_, __, m):
    return bool(m.chat) and m.chat.id == DB_CHANNEL


db_channel_filter = filters.create(_in_db_channel)  # follows DB_CHANNEL even after /dbset


@app.on_message(db_channel_filter & (filters.document | filters.video | filters.audio))
async def index_file(_, m: Message):
    await index_message(m)


# ----------------------------------------------------------------------------
# AUTO FORWARD: new messages from SOURCE_GROUPS -> DB_CHANNEL (and indexed instantly)
# ----------------------------------------------------------------------------
if SOURCE_GROUPS:

    @app.on_message(filters.chat(SOURCE_GROUPS) & ~filters.service, group=1)
    async def auto_forward(_, m: Message):
        media = m.document or m.video or m.audio
        if not media and not FORWARD_ALL:
            return

        uid = media.file_unique_id if media else None
        if uid and await store.is_forwarded(uid):
            return  # this file has already been forwarded

        try:
            sent = await m.copy(DB_CHANNEL)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            sent = await m.copy(DB_CHANNEL)
        except Exception as e:
            log.error("Auto-forward failed (group %s): %s", m.chat.id, e)
            return

        if uid:
            await store.mark_forwarded(uid)
            await index_message(sent)


# ----------------------------------------------------------------------------
# INDEXING OLD FILES (files that were in the DB channel before the bot started)
# Bots can't read channel history directly, so message ids from 1 to the last id
# are scanned in batches using get_messages.
# ----------------------------------------------------------------------------
_scan_lock = asyncio.Lock()


async def get_last_message_id() -> int:
    try:
        tmp = await app.send_message(DB_CHANNEL, "¤ indexing...", disable_notification=True)
        last_id = tmp.id
        try:
            await tmp.delete()
        except Exception:
            pass
        return last_id
    except Exception as e:
        if DB_LAST_MESSAGE_ID:
            log.warning("Could not post in the DB channel (%s). Using DB_LAST_MESSAGE_ID.", e)
            return DB_LAST_MESSAGE_ID
        raise RuntimeError(f"Could not post in the DB channel (is the bot an admin?): {e}")


async def scan_db_channel(full: bool = False, progress=None):
    """Returns (found, last_id). full=True = complete scan from the start."""
    async with _scan_lock:
        last_id = await get_last_message_id()
        start = 1 if full else int(await store.get_meta("last_scanned", "0")) + 1
        found = 0
        for first in range(start, last_id + 1, 200):
            ids = list(range(first, min(first + 200, last_id + 1)))
            try:
                msgs = await app.get_messages(DB_CHANNEL, ids)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                msgs = await app.get_messages(DB_CHANNEL, ids)
            for msg in msgs:
                if msg and not msg.empty and await index_message(msg):
                    found += 1
            if progress:
                await progress(ids[-1], last_id, found)
            await asyncio.sleep(0.5)

        await store.set_meta("last_scanned", str(last_id))
        log.info("Scan finished: %s files indexed (last id %s)", found, last_id)
        return found, last_id


# ----------------------------------------------------------------------------
# MIRROR: every message a user sends to the bot is also posted in the auto-reply group
# ----------------------------------------------------------------------------
@app.on_message(filters.private & ~filters.service, group=-1)
async def mirror_handler(client: Client, m: Message):
    user = m.from_user
    if not AUTO_GROUP or not user or user.is_bot:
        return
    if user.id in ALL_ADMINS and not MIRROR_ADMINS:
        return
    if m.text and m.text.split()[0].split("@")[0].lower() == "/start":
        return  # /start already has its own card
    mirror_user_message(m)


# ----------------------------------------------------------------------------
# USER COMMANDS
# ----------------------------------------------------------------------------
async def open_home(client: Client, chat_id: int, user):
    """Language -> Force Join -> Pending File / Welcome."""

    # STEP 1: Language selection
    if not await has_chosen_lang(user.id):
        return await client.send_message(
            chat_id,
            lang_pick_text(),
            reply_markup=lang_keyboard(),
            link_preview_options=NO_PREVIEW,
        )

    # STEP 2: Force Join check
    lang = await lang_of(user)
    missing = await not_joined(client, user.id)

    if missing:
        text, kb = await join_view(missing, lang)
        return await client.send_message(
            chat_id,
            text,
            reply_markup=kb,
            link_preview_options=NO_PREVIEW,
        )

    # STEP 3: Pending File or Welcome
    if await deliver_pending(client, user, chat_id, lang):
        return

    await send_welcome(client, chat_id, user, lang)


@app.on_message(filters.command("start") & user_place)
async def start_cmd(client: Client, m: Message):

    if m.chat.id > 0:
        is_new = await register_user(m.from_user.id)
        await log_start(client, m.from_user, is_new)

        wanted = (
            re.fullmatch(r"f(\d{1,12})", m.command[1])
            if len(m.command) > 1 else None
        )

        if wanted:
            if len(_pending_file) > 5000:
                _pending_file.clear()

            _pending_file[m.from_user.id] = int(wanted.group(1))

    await open_home(client, m.chat.id, m.from_user)

@app.on_message(filters.command("language") & user_place)
async def language_cmd(_, m: Message):
    await m.reply(lang_pick_text(), reply_markup=lang_keyboard(), quote=True)


@app.on_callback_query(filters.regex(r"^lang$"))
async def lang_open_cb(_, cq: CallbackQuery):
    await edit(cq.message, lang_pick_text(), lang_keyboard())
    await cq.answer()


@app.on_callback_query(filters.regex(r"^lg\|"))
async def lang_cb(client: Client, cq: CallbackQuery):

    code = cq.data.split("|", 1)[1]

    if code not in LANGS:
        return await cq.answer()

    await set_lang(cq.from_user.id, code)

    await cq.answer(
        tr(code, "lang_set", lang=LANGS[code][0])
    )

    try:
        await cq.message.delete()
    except Exception:
        pass

    await open_home(
        client,
        cq.message.chat.id,
        cq.from_user,
    )


@app.on_message(filters.command("help") & user_place)
async def help_cmd(_, m: Message):
    lang = await lang_of(m.from_user)
    await m.reply(
        help_text(is_admin_id(m.from_user.id), m.from_user.id in ADMINS, lang),
        reply_markup=back_keyboard(lang),
        quote=True,
    )


# ----------------------------------------------------------------------------
# ADMIN COMMANDS
# ----------------------------------------------------------------------------
@app.on_message(filters.command("stats") & admin_place & admin_filter)
async def stats_cmd(_, m: Message):
    files = await store.count_files()
    users = await store.count_users()
    channels = len(await get_force_channels())
    kind = "MongoDB ✓ (permanent)" if store.persistent else "SQLite ▲ (may be lost on restart)"
    db_lines = ""
    if hasattr(store, "status"):
        icons = {"active": "✓ Active", "full": "✗ Full", "standby": "◇ Standby"}
        try:
            for d in await store.status():
                db_lines += (
                    f"   ◇ DB {d['n']}: {d['used_mb']:.0f} MB • {d['files']} files • {icons[d['state']]}\n"
                )
        except Exception as e:
            log.warning("Could not read database status: %s", e)
    await m.reply(
        "□ <b>Bot Statistics</b>\n"
        + LINE
        + f"\n☆ Files: <b>{files}</b>\n"
        f"♧ Users: <b>{users}</b>\n"
        f"♛ Admins: <b>{len(ALL_ADMINS)}</b>\n"
        f"◇ Force-join channels: <b>{channels}</b>\n"
        f"¤ Auto-forward groups: <b>{len(SOURCE_GROUPS)}</b>\n"
        f"◇ Auto-delete: <b>{minutes() if AUTO_DELETE_SECONDS > 0 else 'off'}"
        f"{' min' if AUTO_DELETE_SECONDS > 0 else ''}</b>\n"
        f"□ Database: {kind}\n{db_lines}"
        f"◇ Uptime: <b>{fmt_uptime(time.time() - START_TIME)}</b>\n"
        + LINE,
        quote=True,
    )


# ---------- ADD / REMOVE ADMINS (only owners from env ADMINS) ----------
async def resolve_target(client: Client, m: Message):
    """User id from: reply, numeric id or @username."""
    if m.reply_to_message and m.reply_to_message.from_user:
        return m.reply_to_message.from_user.id
    if len(m.command) > 1:
        arg = m.command[1].lstrip("@")
        if arg.lstrip("-").isdigit():
            return int(arg)
        try:
            return (await client.get_users(arg)).id
        except Exception:
            return None
    return None


@app.on_message(filters.command("addadmin") & admin_place & owner_filter)
async def addadmin_cmd(client: Client, m: Message):
    uid = await resolve_target(client, m)
    if not uid:
        return await m.reply(
            "♤ <b>Add Admin</b>\n"
            + LINE
            + "\n<code>/addadmin 123456789</code>\n"
            "<code>/addadmin @username</code>\n"
            "or <b>reply</b> to a user's message with <code>/addadmin</code>",
            quote=True,
        )
    if uid in ALL_ADMINS:
        return await m.reply("¤ This user is already an admin.", quote=True)
    ALL_ADMINS.add(uid)
    await save_admins()
    await set_menu_commands()
    try:
        await client.send_message(
            uid, "♛ <b>Congratulations!</b> You are now an <b>Admin</b> of this bot. Send /help to see the commands."
        )
    except Exception:
        pass
    await m.reply(f"✓ <b>Admin Added</b>\n{LINE}\n♡ ID: <code>{uid}</code>", quote=True)


@app.on_message(filters.command("deladmin") & admin_place & owner_filter)
async def deladmin_cmd(client: Client, m: Message):
    uid = await resolve_target(client, m)
    if not uid:
        return await m.reply("Usage: <code>/deladmin 123456789</code> or reply to the user.", quote=True)
    if uid in ADMINS:
        return await m.reply("¤ Owners (set in env ADMINS) can't be removed.", quote=True)
    if uid not in ALL_ADMINS:
        return await m.reply("¤ This user is not an admin.", quote=True)
    ALL_ADMINS.discard(uid)
    await save_admins()
    try:
        await client.set_bot_commands(
            [BotCommand("start", "Start the bot"), BotCommand("help", "How to use")],
            scope=BotCommandScopeChat(uid),
        )
    except Exception:
        pass
    await m.reply(f"✗ <b>Admin Removed</b>\n{LINE}\n♡ ID: <code>{uid}</code>", quote=True)


@app.on_message(filters.command("admins") & admin_place & admin_filter)
async def admins_cmd(_, m: Message):
    lines = [f"{'♛ Owner' if a in ADMINS else '♡ Admin'}  <code>{a}</code>" for a in sorted(ALL_ADMINS)]
    await m.reply("♛ <b>Admins</b>\n" + LINE + "\n" + "\n".join(lines), quote=True)


# ---------- START IMAGE (admin only) ----------
@app.on_message(filters.command("setstart") & admin_place & admin_filter)
async def setstart_cmd(_, m: Message):
    src = m.reply_to_message if (m.reply_to_message and m.reply_to_message.photo) else m
    if not src.photo:
        return await m.reply(
            "☆ <b>Set Start Image</b>\n"
            + LINE
            + "\nSend a photo with the caption <code>/setstart</code>,\n"
            "or <b>reply</b> to a photo with <code>/setstart</code>.",
            quote=True,
        )
    await store.set_meta("start_pic", src.photo.file_id)
    await m.reply_photo(src.photo.file_id, caption="✓ <b>Start image updated!</b>", quote=True)


@app.on_message(filters.command("delstart") & admin_place & admin_filter)
async def delstart_cmd(_, m: Message):
    await store.set_meta("start_pic", "")
    await m.reply("✗ Start image removed.", quote=True)


@app.on_message(filters.command("broadcast") & admin_place & admin_filter)
async def broadcast_cmd(client: Client, m: Message):
    src = m.reply_to_message
    text = m.text.split(None, 1)[1] if len(m.command) > 1 else None
    if not src and not text:
        return await m.reply(
            "◇ <b>Broadcast</b>\n"
            + LINE
            + "\n<b>Reply</b> to a message with <code>/broadcast</code>,\n"
            "or directly: <code>/broadcast your message</code>",
            quote=True,
        )

    async def send_one(uid: int):
        if src:
            await src.copy(uid)
        else:
            await client.send_message(uid, text, link_preview_options=NO_PREVIEW)

    user_ids = await store.all_user_ids()
    total = len(user_ids)
    status = await m.reply(f"◇ Starting broadcast... <b>{total}</b> users", quote=True)
    ok = blocked = fail = 0
    last_edit = time.time()

    for i, uid in enumerate(user_ids, 1):
        try:
            try:
                await send_one(uid)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await send_one(uid)
            ok += 1
        except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid):
            blocked += 1
            await store.delete_user(uid)  # remove users who blocked the bot from the list
            _known_users.discard(uid)
        except Exception:
            fail += 1

        if time.time() - last_edit > 3:
            last_edit = time.time()
            try:
                await status.edit_text(
                    f"◇ Broadcast in progress...\n{progress_bar(i, total)} <b>{i}/{total}</b>"
                )
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await status.edit_text(
        "✓ <b>Broadcast Complete</b>\n"
        + LINE
        + f"\n◇ Sent: <b>{ok}</b>\n"
        f"✗ Blocked/Deleted (removed from list): <b>{blocked}</b>\n"
        f"▲ Failed: <b>{fail}</b>"
    )


@app.on_message(filters.command("index") & admin_place & admin_filter)
async def index_cmd(_, m: Message):
    full = len(m.command) > 1 and m.command[1].lower() == "full"
    status = await m.reply("◇ Scanning the DB channel, please wait...", quote=True)
    last_edit = [0.0]

    async def progress(done, total, found):
        if time.time() - last_edit[0] < 3:
            return
        last_edit[0] = time.time()
        try:
            await status.edit_text(
                f"◇ Scan in progress...\n{progress_bar(done, total)} <b>{done}/{total}</b>\n"
                f"☆ Files found: <b>{found}</b>"
            )
        except Exception:
            pass

    try:
        found, last_id = await scan_db_channel(full=full, progress=progress)
    except Exception as e:
        return await status.edit_text(
            f"✗ <b>Scan failed</b>\n{esc(e)}\n\nIs the bot an admin in the DB channel and able to post? Please check."
        )
    total = await store.count_files()
    await status.edit_text(
        "✓ <b>Scan Complete</b>\n"
        + LINE
        + f"\n□ Found this time: <b>{found}</b> files\n"
        f"☆ Total indexed: <b>{total}</b>\n"
        f"¤ Last message id: <code>{last_id}</code>"
    )


ADDCHANNEL_USAGE = (
    "+ <b>Add Force-Join Channel</b>\n"
    + LINE
    + "\n<code>/addchannel 1 @username</code>\n"
    "<code>/addchannel 2 -1001234567890</code>\n"
    "<code>/addchannel 3 -1001234567890 https://t.me/+InviteLink</code>\n"
    "<code>/addchannel @username</code> (goes into an empty slot automatically)\n\n"
    "Slots 1 to 10. Using the same slot again replaces the old channel.\n"
    "The bot must be an <b>admin</b> in that channel."
)


@app.on_message(filters.command("addchannel") & admin_place & admin_filter)
async def addchannel_cmd(client: Client, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply(ADDCHANNEL_USAGE, quote=True)

    if re.fullmatch(r"\d{1,2}", args[0]) and len(args) >= 2:
        slot, rest = int(args[0]), args[1:]
    else:
        used = {c["n"] for c in await get_force_channels()}
        slot = next((i for i in range(1, 11) if i not in used), None)
        if slot is None:
            return await m.reply(
                "▲ All 10 slots are full. Give a slot number to replace one, or use /delchannel.",
                quote=True,
            )
        rest = args
    if not 1 <= slot <= 10:
        return await m.reply("▲ Slot must be between 1 and 10.", quote=True)

    ref = parse_chat(rest[0])
    link = rest[1] if len(rest) > 1 else ""

    try:
        chat = await client.get_chat(ref)
    except Exception as e:
        return await m.reply(
            f"✗ <b>Channel not found</b>\n{esc(e)}\n\nFirst make the bot an <b>admin</b> in that channel, then run the command again.",
            quote=True,
        )

    is_admin = False
    try:
        me = await client.get_chat_member(chat.id, "me")
        is_admin = me.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        pass

    if not link:
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            try:
                link = await client.export_chat_invite_link(chat.id)
            except Exception:
                link = ""

    await store.set_channel(slot, str(chat.id), link)

    note = ""
    if not is_admin:
        note += "\n▲ The bot doesn't appear to be an admin in this channel. The join check will only work once it is."
    if not link:
        note += "\n▲ This is a private channel and no link was found. Add an invite link at the end of the command."
    await m.reply(
        "✓ <b>Channel Added</b>\n"
        + LINE
        + f"\n♤ Slot: <b>{slot}</b>\n"
        f"◇ Name: <b>{esc(chat.title)}</b>\n"
        f"¤ ID: <code>{chat.id}</code>\n"
        f"¤ Link: {esc(link) or 'none'}{note}",
        quote=True,
        link_preview_options=NO_PREVIEW,
    )


@app.on_message(filters.command("delchannel") & admin_place & admin_filter)
async def delchannel_cmd(_, m: Message):
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await m.reply("Usage: <code>/delchannel 1</code>", quote=True)
    slot = int(m.command[1])
    await store.del_channel(slot)
    if any(c["n"] == slot for c in ENV_CHANNELS):
        await store.set_channel(slot, "", "")  # disable the slot that comes from env
    await m.reply(f"✗ Slot <b>{slot}</b> removed.", quote=True)


@app.on_message(filters.command("channels") & admin_place & admin_filter)
async def channels_cmd(client: Client, m: Message):
    chans = await get_force_channels()
    if not chans:
        return await m.reply("□ No force-join channels are set. Use /addchannel.", quote=True)

    blocks = []
    for c in chans:
        title, bot_ok = "? Not found", False
        try:
            chat = await client.get_chat(c["ref"])
            title = chat.title
            me = await client.get_chat_member(chat.id, "me")
            bot_ok = me.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
        except Exception:
            pass
        blocks.append(
            f"<b>{c['n']}. {esc(title)}</b>\n"
            f"¤ <code>{c['ref']}</code>\n"
            f"¤ {esc(c['link']) or 'no link'}\n"
            f"♤ Bot: {'✓ Admin' if bot_ok else '▲ Not admin'}"
        )
    await m.reply(
        "◇ <b>Force-Join Channels</b>\n" + LINE + "\n" + "\n\n".join(blocks),
        quote=True,
        link_preview_options=NO_PREVIEW,
    )


# ----------------------------------------------------------------------------
# /sent : admins send a message or a file to a user's DM (works in the bot chat and in the group)
# ----------------------------------------------------------------------------
SENT_USAGE = (
    "✉ <b>Send To User</b>\n"
    + LINE
    + "\n<code>/sent 123456789 your message</code> - text to that user\n"
    "Reply to a file/message with <code>/sent 123456789</code> - sends it to that user\n"
    "Send a file with the caption <code>/sent 123456789 text</code> - file + text\n\n"
    "<b>In the auto-reply group:</b> reply to the user's card/message with\n"
    "<code>/sent your text</code> (or a file with caption <code>/sent text</code>) - no id needed.\n"
    + LINE
)


def target_from_card(reply) -> int:
    """User id from a card/mirrored message that the BOT posted (the 'ID: 123' line)."""
    if reply and reply.from_user and getattr(reply.from_user, "is_self", False):
        found = re.search(r"ID:\s*(\d{4,15})", reply.text or reply.caption or "")
        if found:
            return int(found.group(1))
    return 0


def media_file_id(msg):
    if not msg or not msg.media:
        return None
    return getattr(getattr(msg, msg.media.value, None), "file_id", None)


@app.on_message(filters.command("sent") & admin_place & admin_filter)
async def sent_cmd(client: Client, m: Message):
    raw = (m.text or m.caption or "").strip()
    pieces = raw.split(None, 2)
    reply = m.reply_to_message
    explicit = len(pieces) >= 2 and re.fullmatch(r"\d{5,15}", pieces[1]) is not None
    if explicit:
        uid = int(pieces[1])
        rest = pieces[2].strip() if len(pieces) > 2 else ""
    else:
        uid = target_from_card(reply)
        rest = raw.split(None, 1)[1].strip() if len(pieces) > 1 else ""
    if not uid:
        return await m.reply(SENT_USAGE, quote=True)

    src = None if (not explicit and target_from_card(reply)) else reply  # a card is only context
    no_fmt = enums.ParseMode.DISABLED
    try:
        if media_file_id(m):  # the command message itself carries a file
            kind = m.media.name.lower()
            await client.send_cached_media(uid, media_file_id(m), caption=rest, parse_mode=no_fmt)
        elif rest and src and media_file_id(src):  # replied file + new caption
            kind = src.media.name.lower()
            await client.send_cached_media(uid, media_file_id(src), caption=rest, parse_mode=no_fmt)
        elif rest:
            kind = "text"
            await client.send_message(uid, rest, parse_mode=no_fmt, link_preview_options=NO_PREVIEW)
        elif src:  # copy the replied message as it is (text, file, photo, ...)
            kind = src.media.name.lower() if src.media else "text"
            await src.copy(uid)
        else:
            return await m.reply(SENT_USAGE, quote=True)
    except (UserIsBlocked, InputUserDeactivated):
        return await m.reply(f"✗ <code>{uid}</code> has blocked the bot or deleted the account.", quote=True)
    except PeerIdInvalid:
        return await m.reply(
            f"✗ The bot doesn't know <code>{uid}</code>. The user must press /start in the bot first.",
            quote=True,
        )
    except FloodWait as e:
        return await m.reply(f"▲ Telegram says wait {e.value}s, try again.", quote=True)
    except Exception as e:
        return await m.reply(f"✗ <b>Failed</b>\n{esc(e)}", quote=True)

    await m.reply(f"✓ <b>Sent</b> ({kind}) → <code>{uid}</code>", quote=True)
    if AUTO_GROUP and m.chat.id != AUTO_GROUP:  # keep a record in the group when used in the bot chat
        group_text(
            AUTO_GROUP,
            "✉ <b>Reply Sent To User</b>\n"
            + LINE
            + f"\n¤ ID: <code>{uid}</code>\n"
            f"◇ Type: {kind}\n"
            f"♛ By: {m.from_user.mention}\n"
            f"◇ Time: {now_ist()}",
        )


# ----------------------------------------------------------------------------
# OWNER COMMANDS: /del (delete a file from the database) and /dbset (set the DB channel)
# Only the owners from env ADMINS can use these.
# ----------------------------------------------------------------------------
def del_confirm_view(row: dict):
    title = row.get("title") or f"file_{row['msg_id']}"
    mid = row["msg_id"]
    text = (
        "✗ <b>Delete This File?</b>\n"
        + LINE
        + f"\n{file_icon(title)} <b>{esc(title[:200])}</b>\n"
        f"□ Size: <b>{human(row.get('size', 0))}</b>\n"
        f"¤ Message id: <code>{mid}</code>\n"
        + LINE
        + "\n<b>DB Only</b> = removed from search, the file stays in the channel "
        "(it comes back if you run /index full).\n"
        "<b>DB + Channel</b> = also deleted from the DB channel."
    )
    kb = InlineKeyboardMarkup(
        [
            [
                btn("✗ DB Only", RED, callback_data=f"dly|{mid}|db"),
                btn("✗ DB + Channel", RED, callback_data=f"dly|{mid}|all"),
            ],
            [InlineKeyboardButton("« Cancel", callback_data="dln")],
        ]
    )
    return text, kb


@app.on_message(filters.command("del") & admin_place & owner_filter)
async def del_cmd(_, m: Message):
    arg = m.text.split(None, 1)[1].strip() if len(m.command) > 1 else ""
    if not arg:
        return await m.reply(
            "✗ <b>Delete File</b>\n"
            + LINE
            + "\n<code>/del KGF</code> - search and pick the file to delete\n"
            "<code>/del 1234</code> - delete by message id (DB channel)\n"
            + LINE,
            quote=True,
        )

    if arg.lstrip("#").isdigit():
        row = await store.get_file(int(arg.lstrip("#")))
        if not row:
            return await m.reply("¤ No file with this id in the database.", quote=True)
        text, kb = del_confirm_view(row)
        return await m.reply(text, reply_markup=kb, quote=True)

    results = await store.find(norm(arg).split())
    if not results:
        return await m.reply("¤ Nothing found. Try a shorter name.", quote=True)
    shown = results[:10]
    rows = [
        [
            InlineKeyboardButton(
                f"✗ {human(size)} ┃ {title[:38]}", callback_data=f"dl|{mid}"
            )
        ]
        for mid, title, size, *_ in shown
    ]
    rows.append([InlineKeyboardButton("« Cancel", callback_data="dln")])
    more = f"\n▲ Showing 10 of {len(results)}. Use a more specific name." if len(results) > 10 else ""
    await m.reply(
        "✗ <b>Pick The File To Delete</b>\n" + LINE + f"\n□ Found: <b>{len(results)}</b>{more}",
        reply_markup=InlineKeyboardMarkup(rows),
        quote=True,
    )


@app.on_callback_query(filters.regex(r"^dl\|"))
async def del_pick_cb(_, cq: CallbackQuery):
    if cq.from_user.id not in ADMINS:
        return await cq.answer("Only the owner can do this.", show_alert=True)
    row = await store.get_file(int(cq.data.split("|")[1]))
    if not row:
        return await cq.answer("This file is already removed.", show_alert=True)
    text, kb = del_confirm_view(row)
    await edit(cq.message, text, kb)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^dly\|"))
async def del_yes_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id not in ADMINS:
        return await cq.answer("Only the owner can do this.", show_alert=True)
    _, mid, mode = cq.data.split("|")
    mid = int(mid)
    row = await store.get_file(mid)
    title = (row or {}).get("title") or f"file_{mid}"
    existed = await store.delete_file(mid)
    lines = ["✓ Removed from the database." if existed else "¤ It was not in the database."]
    if mode == "all":
        try:
            await client.delete_messages(DB_CHANNEL, mid)
            lines.append("✓ Deleted from the DB channel.")
        except Exception as e:
            lines.append(f"▲ Could not delete from the channel: {esc(e)}")
    await edit(
        cq.message,
        "✓ <b>Done</b>\n" + LINE + f"\n{file_icon(title)} <b>{esc(title[:200])}</b>\n" + "\n".join(lines),
    )
    await cq.answer("Deleted ✓")


@app.on_callback_query(filters.regex(r"^dln$"))
async def del_no_cb(_, cq: CallbackQuery):
    await edit(cq.message, "✗ Cancelled.")
    await cq.answer()


@app.on_message(filters.command("dbset") & admin_place & owner_filter)
async def dbset_cmd(client: Client, m: Message):
    if len(m.command) < 2:
        files = await store.count_files()
        return await m.reply(
            "♤ <b>Database Channel</b>\n"
            + LINE
            + f"\n¤ Current: <code>{DB_CHANNEL}</code>\n"
            f"☆ Files indexed: <b>{files}</b>\n"
            + LINE
            + "\n<code>/dbset -1001234567890</code>\n"
            "<code>/dbset @channelusername</code>\n\n"
            "The bot must be an <b>admin</b> in the new channel.",
            quote=True,
        )

    ref = parse_chat(m.command[1])
    try:
        chat = await client.get_chat(ref)
    except Exception as e:
        return await m.reply(
            f"✗ <b>Channel not found</b>\n{esc(e)}\n\nFirst make the bot an <b>admin</b> in that channel, then try again.",
            quote=True,
        )

    try:
        me = await client.get_chat_member(chat.id, "me")
        bot_ok = me.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        bot_ok = False
    if not bot_ok:
        return await m.reply(
            f"✗ The bot is not an <b>admin</b> in <b>{esc(chat.title)}</b>.\nMake it an admin and run the command again.",
            quote=True,
        )
    if chat.id == DB_CHANNEL:
        return await m.reply("¤ This is already the database channel.", quote=True)

    kb = InlineKeyboardMarkup(
        [
            [btn("✓ Keep Old Files", GREEN, callback_data=f"dbs|keep|{chat.id}")],
            [btn("✗ Clear Old Files", RED, callback_data=f"dbs|clear|{chat.id}")],
            [InlineKeyboardButton("« Cancel", callback_data="dln")],
        ]
    )
    await m.reply(
        "♤ <b>Change Database Channel?</b>\n"
        + LINE
        + f"\n◇ New: <b>{esc(chat.title)}</b>\n"
        f"¤ ID: <code>{chat.id}</code>\n"
        f"☆ Files in database now: <b>{await store.count_files()}</b>\n"
        + LINE
        + "\n<b>Keep Old Files</b> = old files stay searchable (they are sent with their saved file id). "
        "Message ids start from 1 in every channel, so a few old entries can get replaced.\n"
        "<b>Clear Old Files</b> = the database is emptied and only the new channel is indexed.\n\n"
        "The new channel is scanned fully after you choose.",
        reply_markup=kb,
        quote=True,
    )


async def _scan_after_dbset(msg: Message):
    try:
        found, last_id = await scan_db_channel(full=True)
        total = await store.count_files()
        text = (
            "✓ <b>Database Channel Updated</b>\n"
            + LINE
            + f"\n□ Files found in new channel: <b>{found}</b>\n"
            f"☆ Total in database: <b>{total}</b>\n"
            f"¤ Last message id: <code>{last_id}</code>"
        )
    except Exception as e:
        text = (
            f"▲ <b>Channel saved, but the scan failed</b>\n{esc(e)}\n\n"
            "Make sure the bot is an admin there and can post, then run /index full."
        )
    await edit(msg, text)


@app.on_callback_query(filters.regex(r"^dbs\|"))
async def dbset_cb(client: Client, cq: CallbackQuery):
    global DB_CHANNEL
    if cq.from_user.id not in ADMINS:
        return await cq.answer("Only the owner can do this.", show_alert=True)
    _, mode, cid = cq.data.split("|")
    if mode == "clear":
        await store.clear_files()
    DB_CHANNEL = int(cid)
    await store.set_meta("db_channel", str(DB_CHANNEL))
    await store.set_meta("last_scanned", "0")
    await edit(
        cq.message,
        "⏳ <b>Database channel changed.</b>\n" + LINE + f"\n¤ New: <code>{DB_CHANNEL}</code>\nScanning the channel, please wait...".replace("⏳", "◇"),
    )
    await cq.answer("Saved ✓")
    task = asyncio.create_task(_scan_after_dbset(cq.message))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# ----------------------------------------------------------------------------
# SEARCH
# ----------------------------------------------------------------------------
_search_cache: dict = {}


_filter_cache: dict = {}  # token -> {"q": "1080p", "l": "hin", "s": "1"}


def cache_query(token: str, query: str):
    _search_cache[token] = query
    _filter_cache.pop(token, None)
    while len(_search_cache) > 500:
        old = next(iter(_search_cache))
        _search_cache.pop(old)
        _filter_cache.pop(old, None)


_EXT_RE = re.compile(
    r"\.(mkv|mp4|avi|mov|webm|m4v|ts|flv|wmv|mp3|m4a|ogg|wav|flac|pdf|epub|mobi|azw3|zip|rar|7z|srt|txt|doc|docx)$",
    re.I,
)
_URL_RE = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/)[^\s\]\)\}\[\(\{<>\"']+", re.I)
_DOMAIN_RE = re.compile(
    r"(?<![\w@/])([A-Za-z0-9-]{4,})\.(?:com|net|org|in|me|xyz|info|io|cc|tv|app|site|online|club|vip|live|link|"
    r"top|biz|ws|pw|fun|cam|lol|nl|ink|wiki|click|lat|space|store|tech|cyou|monster|ltd)\b(?:/\S*)?",
    re.I,
)
_MENTION_RE = re.compile(r"@([A-Za-z0-9_]{3,})")
_NOT_A_SITE = {
    "hindi", "dual", "audio", "webrip", "web-dl", "bluray", "brrip", "hdrip", "hdtv", "x264", "x265", "hevc",
    "esub", "english", "tamil", "telugu", "malayalam", "kannada", "bengali", "punjabi", "1080p", "720p",
    "480p", "2160p", "4k", "season", "complete", "movie", "movies",
}


def _domain_sub(m):
    return m.group(0) if m.group(1).lower() in _NOT_A_SITE else " "


def _mention_sub(m):
    return m.group(0) if BOT_USERNAME and m.group(1).lower() == BOT_USERNAME.lower() else " "


def clean_title(title: str) -> str:
    """File name without links / site names / other @usernames (only the bot's own @username stays)."""
    title = title or ""
    ext_m = _EXT_RE.search(title)
    ext = ext_m.group(0) if ext_m else ""
    base = title[: ext_m.start()] if ext_m else title
    base = _URL_RE.sub(" ", base)
    base = _DOMAIN_RE.sub(_domain_sub, base)
    base = _MENTION_RE.sub(_mention_sub, base)
    base = re.sub(r"\[\s*[-_|.]*\s*\]|\(\s*[-_|.]*\s*\)|\{\s*[-_|.]*\s*\}", " ", base)
    base = re.sub(r"\s{2,}", " ", base)
    base = re.sub(r"(?:\s[-_|•·~+:,]){2,}", " -", base)
    base = base.strip(" -_|•·:~+,.")
    return (base or "File") + "@OVN3RS" + ext


def file_meta(title: str, extra: str = ""):
    """(quality, [language codes], [seasons]) read from the file name (+ caption/search text)."""
    text = f"{title or ''} {extra or ''}"
    return detect_quality(text), detect_languages(text), detect_seasons(text)


def phonetic_rank(words, candidates):
    """Keeps files whose name sounds like the query (salam = salaam = सलाम), best match first."""
    keys = phonetic_words(" ".join(words))
    if not keys:
        return []
    need = len(keys) if len(keys) <= 3 else math.ceil(len(keys) * 0.7)
    scored = []
    for row in candidates:
        have = set(phonetic_words(f"{row[1]} {row[3] if len(row) > 3 else ''}"))
        hits = sum(1 for k in keys if k in have)
        if hits >= need:
            scored.append((-hits, (row[1] or "").lower(), row))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in scored]


async def run_search(query: str):
    """(results, fuzzy). Understands other scripts (Hindi, Tamil...) and different spellings."""
    words = norm(query).split()
    results = await store.find(words)
    if results:
        return results, False

    latin = to_latin(query)  # "मां तुझे सलाम" -> "man tujhe salam"
    lwords = norm(latin).split() if latin != query else words
    if lwords and lwords != words:
        results = await store.find(lwords)
        if results:
            return results, False

    if lwords:  # spelling-tolerant: salam = salaam, maan = maa ...
        prefixes = list({w[:3] for w in lwords if len(w) >= 2})
        candidates = await store.find_any(prefixes, limit=600) if prefixes else []
        results = phonetic_rank(lwords, candidates)
        if results:
            return results, True

    if len(lwords) >= 2:
        useful = [w for w in lwords if len(w) >= 3] or lwords
        results = await store.find_any(useful)
        if results:
            return results, True
    return [], False


async def build_page(query: str, page: int, token: str, lang: str = "en", group_links: bool = False):
    all_results, fuzzy = await run_search(query)
    if not all_results:
        return None, None

    # quality / language / season are read from the file names
    metas = [(r, file_meta(r[1], r[3] if len(r) > 3 else "")) for r in all_results]
    sel = _filter_cache.setdefault(token, {})

    def ok(meta, skip=""):
        q, langs, seasons = meta
        if skip != "q" and sel.get("q") and q != sel["q"]:
            return False
        if skip != "l" and sel.get("l") and sel["l"] not in langs:
            return False
        if skip != "s" and sel.get("s") and int(sel["s"]) not in seasons:
            return False
        return True

    results = [r for r, meta in metas if ok(meta)]
    if not results:  # the chosen filters match nothing, show everything again
        sel.clear()
        results = list(all_results)

    # options for each filter row (counted with the OTHER filters applied)
    q_counts, l_counts, s_counts = {}, {}, {}
    for _, meta in metas:
        q, langs, seasons = meta
        if q and ok(meta, "q"):
            q_counts[q] = q_counts.get(q, 0) + 1
        if ok(meta, "l"):
            for lg in langs:
                l_counts[lg] = l_counts.get(lg, 0) + 1
        if ok(meta, "s"):
            for sn in seasons:
                s_counts[sn] = s_counts.get(sn, 0) + 1
    q_opts = sorted(q_counts.items(), key=lambda kv: QUALITY_ORDER.index(kv[0]))
    l_opts = sorted(l_counts.items(), key=lambda kv: LANG_ORDER.index(kv[0]))
    s_opts = sorted(s_counts.items())

    def facet_rows(kind, options, label, per_row, cap=12):
        if not options or (len(options) < 2 and not sel.get(kind)):
            return []
        buttons = []
        for value, count in options[:cap]:
            active = str(sel.get(kind)) == str(value)
            buttons.append(
                btn(
                    f"{'✓ ' if active else ''}{label(value)} ({count})",
                    GREEN if active else None,
                    callback_data=f"f|{kind}|{value}|{token}",
                )
            )
        return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]

    total = len(results)
    pages = max(math.ceil(total / RESULTS_PER_PAGE), 1)
    page = min(max(page, 0), pages - 1)
    chunk = results[page * RESULTS_PER_PAGE:(page + 1) * RESULTS_PER_PAGE]

    text = (
        f"¤ <b>{tr(lang, 'results')}</b>\n"
        + LINE
        + f"\n□ {tr(lang, 'query')}: <i>{esc(query[:60])}</i>\n"
        f"□ {tr(lang, 'found')}: <b>{total}</b>  •  {tr(lang, 'page')} <b>{page + 1}/{pages}</b>\n"
    )
    active_parts = []
    if sel.get("q"):
        active_parts.append(sel["q"])
    if sel.get("l"):
        active_parts.append(LANG_NAMES.get(sel["l"], sel["l"]))
    if sel.get("s"):
        active_parts.append(f"S{int(sel['s']):02d}")
    if active_parts:
        text += f"◇ {tr(lang, 'filter')}: <b>{' • '.join(active_parts)}</b>\n"
    if fuzzy:
        text += f"¤ <i>{tr(lang, 'no_exact')}</i>\n"
    text += LINE + f"\n▼ <b>{tr(lang, 'choose')}</b>"

    rows = []
    rows += facet_rows("q", q_opts, lambda v: v, 3)
    rows += facet_rows("l", l_opts, lambda v: LANG_NAMES[v], 3)
    rows += facet_rows("s", s_opts, lambda v: f"S{v:02d}", 4)
    if active_parts:
        rows.append([InlineKeyboardButton(f"◇ {tr(lang, 'b_clear')}", callback_data=f"f|x|all|{token}")])

    for mid, title, size, *_ in chunk:
        label = f"{file_icon(title)} {human(size)} ┃ {clean_title(title)[:38]}"
        if group_links and BOT_USERNAME:
            # in a group the file is NOT sent: the button opens the bot, which sends the file in private
            rows.append([InlineKeyboardButton(label, url=f"https://t.me/{BOT_USERNAME}?start=f{mid}")])
        else:
            rows.append([InlineKeyboardButton(label, callback_data=f"get|{mid}")])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("«", callback_data=f"pg|{page - 1}|{token}"))
        nav.append(InlineKeyboardButton(f"□ {page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton("»", callback_data=f"pg|{page + 1}|{token}"))
        rows.append(nav)
    rows.append([btn(f"× {tr(lang, 'b_close')} ×", RED, callback_data="close")])
    return text, InlineKeyboardMarkup(rows)


def not_found_text(query: str, lang: str = "en") -> str:
    return (
        f"¤ <b>{tr(lang, 'nf_title')}</b>\n"
        + LINE
        + f"\n¤ <i>{esc(query[:60])}</i>\n\n"
        f"♤ <b>{tr(lang, 'nf_try')}:</b>\n"
        f"• {tr(lang, 'nf1')}\n"
        f"• {tr(lang, 'nf2')}\n"
        f"• {tr(lang, 'nf3')}\n"
        + LINE
    )


@app.on_message(
    filters.text
    & filters.private
    & ~filters.command(
        [
            "start", "help", "stats", "broadcast", "addchannel", "delchannel", "channels", "index",
            "addadmin", "deladmin", "admins", "setstart", "delstart", "del", "dbset", "sent", "language", "search", "s", "movie",
        ]
    )
)
async def search_handler(client: Client, m: Message):
    await register_user(m.from_user.id)
    await do_search(client, m, m.text[:100])


async def do_search(client: Client, m: Message, query: str):
    """Searches `query` and replies with the result page (private chat or group)."""
    lang = await lang_of(m.from_user)
    missing = await not_joined(client, m.from_user.id)
    if missing:
        text, kb = await join_view(missing, lang)
        return await m.reply(text, reply_markup=kb, quote=True)

    try:
        await client.send_chat_action(m.chat.id, enums.ChatAction.TYPING)
    except Exception:
        pass

    token = f"{m.chat.id}{m.from_user.id}{m.id}"
    cache_query(token, query)
    text, kb = await build_page(query, 0, token, lang, m.chat.id < 0)

    if not text:
        log_movie_request(m.from_user, query)
        rows = []
        if SUPPORT_USERNAME:
            rows.append([btn(f"♡ {tr(lang, 'b_support')}", BLUE, url=f"https://t.me/{SUPPORT_USERNAME}")])
        rows.append([btn(f"× {tr(lang, 'b_close')} ×", RED, callback_data="close")])
        reply = await m.reply(
            not_found_text(query, lang),
            reply_markup=InlineKeyboardMarkup(rows),
            quote=True,
        )
        schedule_delete(reply, m)
        return

    reply = await m.reply(text, reply_markup=kb, quote=True)
    schedule_delete(reply, m)


@app.on_message(filters.command(["search", "s", "movie"]) & user_place)
async def search_cmd(client: Client, m: Message):
    """/search KGF - works in private chat and in my groups."""
    if not m.from_user:
        return
    query = m.text.split(None, 1)[1].strip()[:100] if len(m.command) > 1 else ""
    lang = await lang_of(m.from_user)
    if not query:
        return await m.reply(f"☆ {tr(lang, 'step1')}: <code>/search KGF</code>", quote=True)
    if m.chat.id > 0:
        await register_user(m.from_user.id)
    await do_search(client, m, query)


if GROUP_TEXT_SEARCH:

    @app.on_message(
        filters.text & filters.group & filters.create(_in_search_groups) & ~filters.regex(r"^/"),
        group=2,
    )
    async def group_text_search(client: Client, m: Message):
        user = m.from_user
        if not user or user.is_bot or not (2 <= len(m.text.strip()) <= 100):
            return
        await do_search(client, m, m.text.strip())


# ----------------------------------------------------------------------------
# CALLBACKS
# ----------------------------------------------------------------------------
@app.on_callback_query(filters.regex(r"^recheck$"))
async def recheck_cb(client: Client, cq: CallbackQuery):

    lang = await lang_of(cq.from_user)
    missing = await not_joined(client, cq.from_user.id)

    if missing:
        await cq.answer(
            tr(lang, "a_notjoined"),
            show_alert=True,
        )

        text, kb = await join_view(missing, lang)
        await edit(cq.message, text, kb)
        return

    await cq.answer("☆ " + tr(lang, "a_thanks"))

    try:
        await cq.message.delete()
    except Exception:
        pass

    await open_home(
        client,
        cq.message.chat.id,
        cq.from_user,
    )

async def show_home(client: Client, cq: CallbackQuery, lang: str):
    """Welcome screen. If the start picture is set and the message is plain text (after Help), the
    picture is sent again."""
    pic = await store.get_meta("start_pic", "") or START_PIC
    if pic and not cq.message.photo:
        try:
            await cq.message.delete()
        except Exception:
            pass
        await send_welcome(client, cq.message.chat.id, cq.from_user, lang)
    else:
        await edit(cq.message, welcome_text(cq.from_user, lang), home_keyboard(lang))


@app.on_callback_query(filters.regex(r"^home$"))
async def home_cb(client: Client, cq: CallbackQuery):
    await cq.answer()
    await show_home(client, cq, await lang_of(cq.from_user))


@app.on_callback_query(filters.regex(r"^help$"))
async def help_cb(_, cq: CallbackQuery):
    await cq.answer()  # first answer, so the button never keeps "loading"
    lang = await lang_of(cq.from_user)
    await edit(
        cq.message,
        help_text(is_admin_id(cq.from_user.id), cq.from_user.id in ADMINS, lang),
        back_keyboard(lang),
    )


@app.on_callback_query(filters.regex(r"^about$"))
async def about_cb(_, cq: CallbackQuery):
    await cq.answer()
    lang = await lang_of(cq.from_user)
    await edit(cq.message, await about_text(lang), back_keyboard(lang))


@app.on_callback_query(filters.regex(r"^noop$"))
async def noop_cb(_, cq: CallbackQuery):
    await cq.answer()


@app.on_callback_query(filters.regex(r"^close$"))
async def close_cb(_, cq: CallbackQuery):
    try:
        await cq.message.delete()
    except Exception:
        await cq.answer(tr(await lang_of(cq.from_user), "a_closefail"), show_alert=True)
        return
    await cq.answer()


@app.on_callback_query(filters.regex(r"^f\|"))
async def filter_cb(client: Client, cq: CallbackQuery):
    _, kind, value, token = cq.data.split("|", 3)
    query = _search_cache.get(token)
    if not query:
        return await cq.answer(tr(await lang_of(cq.from_user), "a_expired"), show_alert=True)
    sel = _filter_cache.setdefault(token, {})
    if kind == "x":
        sel.clear()
    elif sel.get(kind) == value:
        sel.pop(kind)  # pressing the selected button again clears it
    else:
        sel[kind] = value
    text, kb = await build_page(query, 0, token, await lang_of(cq.from_user), cq.message.chat.id < 0)
    if text:
        await edit(cq.message, text, kb)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^pg\|"))
async def page_cb(client: Client, cq: CallbackQuery):
    _, page, token = cq.data.split("|", 2)
    query = _search_cache.get(token)
    if not query:
        return await cq.answer(tr(await lang_of(cq.from_user), "a_expired"), show_alert=True)
    text, kb = await build_page(query, int(page), token, await lang_of(cq.from_user), cq.message.chat.id < 0)
    if text:
        await edit(cq.message, text, kb)
    await cq.answer()


def file_caption(title: str, size: int, lang: str = "en") -> str:
    q, langs, seasons = file_meta(title)
    text = (
        f"{file_icon(title)} <b>{esc(clean_title(title)[:200])}</b>\n"
        + LINE
        + f"\n□ {tr(lang, 'size')}: <b>{human(size)}</b>\n"
    )
    if q:
        text += f"◇ Quality: <b>{esc(q)}</b>\n"
    if langs:
        text += "◇ Language: <b>" + esc(", ".join(LANG_NAMES.get(x, x) for x in langs)) + "</b>\n"
    if seasons:
        text += "◇ Season: <b>" + ", ".join(f"S{int(x):02d}" for x in sorted(seasons)) + "</b>\n"
    if AUTO_DELETE_SECONDS > 0:
        text += f"◇ {tr(lang, 'f_autodel', minutes=minutes())}\n"
    text += LINE + f"\n✓ <i>{tr(lang, 'save_now')}</i>"
    if BOT_USERNAME:
        text += f"\n♧ @{BOT_USERNAME}"
    return text[:1024]


_pending_file: dict = {}  # user id -> file waiting while he chooses a language / joins the channels


async def send_file(client: Client, user, lang: str, msg_id: int):
    """Sends one file to the user in private. Returns the sent message or None."""
    row = await store.get_file(msg_id)
    title = (row or {}).get("title") or f"file_{msg_id}"
    size = (row or {}).get("size", 0)
    caption = file_caption(title, size, lang)
    kb = file_keyboard(lang)
    sent = None

    # 1) Send using the file_id saved in the database (works even after a restart)
    if row and row.get("file_id"):
        try:
            sent = await client.send_cached_media(user.id, row["file_id"], caption=caption, reply_markup=kb)
        except Exception as e:
            log.warning("Could not send via file_id (%s), trying to copy from the channel", e)

    # 2) Fallback: copy from the DB channel
    if not sent:
        try:
            sent = await client.copy_message(user.id, DB_CHANNEL, msg_id, caption=caption, reply_markup=kb)
        except Exception as e:
            log.error("Error while sending file: %s", e)
            return None

    log_file_sent(user, title, size)
    schedule_delete(sent)
    return sent


async def deliver_pending(client: Client, user, chat_id: int, lang: str) -> bool:
    """A file was asked for with a group button (/start f123): send it now. True if there was one."""
    msg_id = _pending_file.pop(user.id, None)
    if msg_id is None:
        return False
    if not await send_file(client, user, lang, msg_id):
        await client.send_message(chat_id, tr(lang, "a_filefail"))
    return True


@app.on_callback_query(filters.regex(r"^get\|"))
async def get_cb(client: Client, cq: CallbackQuery):
    lang = await lang_of(cq.from_user)
    missing = await not_joined(client, cq.from_user.id)
    if missing:
        await cq.answer(tr(lang, "a_joinfirst"), show_alert=True)
        text, kb = await join_view(missing, lang)
        try:
            return await client.send_message(cq.from_user.id, text, reply_markup=kb)
        except Exception:
            return  # (group user who never started the bot: the alert above is enough)

    msg_id = int(cq.data.split("|")[1])
    if not await send_file(client, cq.from_user, lang, msg_id):
        if cq.message.chat.id < 0 and BOT_USERNAME:  # pressed in a group, but the bot can't write to him
            return await cq.answer(
                tr(lang, "a_startbot"), show_alert=True, url=f"https://t.me/{BOT_USERNAME}?start=go"
            )
        return await cq.answer(tr(lang, "a_filefail"), show_alert=True)
    await cq.answer(f"□ {tr(lang, 'a_filesent')} ✓")

# ----------------------------------------------------------------------------
# START
# ----------------------------------------------------------------------------
async def notify_admins(text: str):
    for admin in list(ALL_ADMINS)[:5]:
        try:
            await app.send_message(admin, text)
        except Exception:
            pass


async def _startup_scan():
    try:
        found, last_id = await scan_db_channel(full=False)
        total = await store.count_files()
        text = (
            "✓ <b>Bot Started</b>\n"
            + LINE
            + f"\n□ New files indexed: <b>{found}</b>\n"
            f"☆ Total files in database: <b>{total}</b>"
        )
        if not store.persistent:
            text += "\n▲ MONGO_URI is not set, data may be lost on restart."
        log.info("Startup index: %s new files, total %s", found, total)
    except Exception as e:
        text = (
            f"✗ <b>Startup index failed</b>\n{esc(e)}\n\n"
            "Make the bot an admin in the DB channel, then run /index full."
        )
        log.error("Startup index failed: %s", e)
    await notify_admins(text)


async def set_menu_commands():
    """Commands shown in Telegram's command menu (when you tap /)."""
    user_cmds = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "How to use"),
        BotCommand("language", "Change language"),
        BotCommand("search", "Search a movie: /search name"),
    ]
    admin_cmds = user_cmds + [
        BotCommand("stats", "Bot statistics"),
        BotCommand("broadcast", "Message everyone"),
        BotCommand("index", "Index the DB channel"),
        BotCommand("addchannel", "Add force-join channel"),
        BotCommand("delchannel", "Remove a channel"),
        BotCommand("channels", "List channels"),
        BotCommand("setstart", "Set start image"),
        BotCommand("delstart", "Remove start image"),
        BotCommand("admins", "List admins"),
        BotCommand("sent", "Send a message/file to a user"),
    ]
    owner_cmds = admin_cmds + [
        BotCommand("addadmin", "Add an admin"),
        BotCommand("deladmin", "Remove an admin"),
        BotCommand("del", "Delete a file from the database"),
        BotCommand("dbset", "Set the database channel"),
    ]
    try:
        await app.set_bot_commands(user_cmds)
        for admin in ALL_ADMINS:
            try:
                cmds = owner_cmds if admin in ADMINS else admin_cmds
                await app.set_bot_commands(cmds, scope=BotCommandScopeChat(admin))
            except Exception:
                pass  # may fail if the admin hasn't started the bot yet
    except Exception as e:
        log.warning("Could not set command menu: %s", e)


async def main():
    global BOT_USERNAME, DB_CHANNEL, _log_queue
    await store.init()
    if hasattr(store, "notify"):
        store.notify = notify_admins  # tells admins when a MongoDB gets full
    await load_admins()
    saved_db = await store.get_meta("db_channel", "")
    if saved_db.lstrip("-").isdigit():
        DB_CHANNEL = int(saved_db)  # channel chosen with /dbset wins over .env
    _known_users.update(await store.all_user_ids())
    await app.start()
    BOT_USERNAME = (await app.get_me()).username or ""
    await resolve_groups()
    _log_queue = asyncio.Queue(maxsize=2000)
    worker = asyncio.create_task(_log_worker())
    _tasks.add(worker)
    log.info("Bot started: @%s", BOT_USERNAME)
    log.info("Admins: %s", sorted(ALL_ADMINS))
    log.info("DB channel: %s", DB_CHANNEL)
    log.info("Log group: %s | Auto-reply group: %s", LOG_GROUP or "none", AUTO_GROUP or "none")
    log.info("Groups where users can use commands: %s", sorted(USER_GROUP_IDS) or "none")
    log.info("Force-join channels: %s", [c["ref"] for c in await get_force_channels()])
    log.info("Auto-forward source groups: %s", SOURCE_GROUPS or "none")
    log.info("Database: %s", "MongoDB" if store.persistent else "SQLite")
    await set_menu_commands()
    if AUTO_INDEX_ON_START:
        asyncio.create_task(_startup_scan())
    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(main())
