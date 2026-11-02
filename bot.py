import asyncio
import html
import logging
import math
import os
import re
import time

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
    Message,
)

from storage import MongoStore, SqliteStore

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

# Database: provide MONGO_URI so data survives restarts (recommended)
MONGO_URI = env("MONGO_URI")
MONGO_DB_NAME = env("MONGO_DB_NAME", "bookbot")
DB_PATH = env("DB_PATH", "files.db")  # only used when MONGO_URI is not set

# Auto-forward: new messages/files from these groups are copied to DB_CHANNEL automatically
SOURCE_GROUPS = [int(x) for x in env("SOURCE_GROUPS").replace(",", " ").split() if x.lstrip("-").isdigit()]
FORWARD_ALL = env_bool("FORWARD_ALL", "false")  # true = forward text messages too

# Files in the DB channel get indexed as soon as the bot starts
AUTO_INDEX_ON_START = env_bool("AUTO_INDEX_ON_START", "true")
# If the bot can't post in the DB channel, give the last message id here for scanning
DB_LAST_MESSAGE_ID = int(env("DB_LAST_MESSAGE_ID", "0") or 0)

BOT_NAME = env("BOT_NAME", "MOVIE HUB 🎬 Bot")
OWNER_USERNAME = env("OWNER_USERNAME").lstrip("@")
SUPPORT_USERNAME = env("SUPPORT_USERNAME").lstrip("@")
UPDATES_CHANNEL = env("UPDATES_CHANNEL").lstrip("@")
START_PIC = env("START_PIC")  # optional: welcome photo (link or file_id)

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

if MONGO_URI:
    store = MongoStore(MONGO_URI, MONGO_DB_NAME)
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
        return "📕"
    if t.endswith((".epub", ".mobi", ".azw3")):
        return "📗"
    if t.endswith((".doc", ".docx", ".odt")):
        return "📘"
    if t.endswith((".ppt", ".pptx")):
        return "📙"
    if t.endswith((".txt", ".rtf")):
        return "📄"
    if t.endswith((".zip", ".rar", ".7z")):
        return "🗜"
    if t.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
        return "🎞"
    if t.endswith((".mp3", ".m4a", ".ogg", ".wav", ".flac")):
        return "🎧"
    return "📚"


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


def is_admin_id(user_id: int) -> bool:
    return user_id in ADMINS


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


async def edit(msg: Message, text: str, kb=None):
    """Edits either a text message or a photo caption."""
    try:
        if msg.photo or msg.video or msg.animation or msg.document:
            await msg.edit_caption(text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass


# ----------------------------------------------------------------------------
# PREMIUM UI: texts + buttons
# ----------------------------------------------------------------------------
def welcome_text(user) -> str:
    if START_TEXT_ENV:
        body = START_TEXT_ENV
    else:
        body = (
            "✨ <b>{bot_name}</b> ✨\n"
            + LINE
            + "\n👋 Hello {mention}!\n\n"
            "🎬 Send me the <b>name</b> of any Movie or Series and I'll find the file and send it instantly.\n\n"
            "┏ 🔍 <b>Fast Search</b>\n"
            "┣ 📥 <b>Instant Delivery</b>\n"
            "┗ ⏳ <b>Auto-delete</b>: {minutes} min\n"
            + LINE
            + "\n💡 <i>Tip: type a short name, like</i> <code>Coolie </code>"
        )
    return body.format(
        mention=user.mention,
        first_name=esc(user.first_name),
        bot_name=esc(BOT_NAME),
        minutes=minutes(),
    )


def help_text(is_admin: bool) -> str:
    text = (
        "🎬 <b>How To Use</b>\n"
        + LINE
        + "\n1️⃣ Send the <b>name</b> of a movie\n"
        "2️⃣ Pick your <b>file</b> from the result list\n"
        f"3️⃣ Once you get the file, <b>save or forward</b> it (it gets deleted in {minutes()} min)\n"
        + LINE
        + "\n💡 <b>Tips</b>\n"
        "• Use a short and simple name\n"
        "• Double-check the spelling\n"
        "• Movie/Series name only, like <code>KGF </code>"
    )
    if is_admin:
        text += (
            "\n\n👑 <b>Admin Commands</b>\n"
            + LINE
            + "\n/stats - bot statistics\n"
            "/broadcast - message everyone (reply to a message or add text)\n"
            "/index - index new files (<code>/index full</code> = full scan)\n"
            "/addchannel - add a force-join channel\n"
            "/delchannel - remove a channel\n"
            "/channels - list channels and their status"
        )
    return text


async def about_text() -> str:
    files = await store.count_files()
    users = await store.count_users()
    text = (
        f"ℹ️ <b>About {esc(BOT_NAME)}</b>\n"
        + LINE
        + f"\n🎬 Files: <b>{files}</b>\n"
        f"👥 Users: <b>{users}</b>\n"
        f"⏳ Auto-delete: <b>{minutes()} min</b>\n"
    )
    if BOT_USERNAME:
        text += f"🤖 Bot: @{BOT_USERNAME}\n"
    if OWNER_USERNAME:
        text += f"👤 Owner: @{esc(OWNER_USERNAME)}\n"
    text += LINE + "\n💙 <i>Keep reading, keep growing.</i>"
    return text


def link_buttons():
    row = []
    if UPDATES_CHANNEL:
        row.append(InlineKeyboardButton("📢 Updates", url=f"https://t.me/{UPDATES_CHANNEL}"))
    if SUPPORT_USERNAME:
        row.append(InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_USERNAME}"))
    return row


def home_keyboard():
    rows = [
        [
            InlineKeyboardButton("🎬 How To Use", callback_data="help"),
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ]
    ]
    links = link_buttons()
    if links:
        rows.append(links)
    if OWNER_USERNAME:
        rows.append([InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}")])
    return InlineKeyboardMarkup(rows)


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]])


def file_keyboard():
    row = link_buttons()
    if OWNER_USERNAME:
        row.append(InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}"))
    return InlineKeyboardMarkup([row]) if row else None


async def send_welcome(m: Message):
    text = welcome_text(m.from_user)
    kb = home_keyboard()
    if START_PIC:
        try:
            return await m.reply_photo(START_PIC, caption=text, reply_markup=kb, quote=True)
        except Exception as e:
            log.warning("Could not send START_PIC (%s), sending text instead", e)
    return await m.reply(text, reply_markup=kb, quote=True, disable_web_page_preview=True)


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


async def join_view(missing):
    """(text, keyboard) - premium join screen with progress."""
    total = len(await get_force_channels())
    joined = max(total - len(missing), 0)
    if JOIN_TEXT_ENV:
        text = JOIN_TEXT_ENV
    else:
        text = (
            "🔒 <b>Access Locked</b>\n"
            + LINE
            + f"\nJoin the <b>{len(missing)}</b> channel(s) below to use this bot.\n\n"
            f"📊 Progress: {progress_bar(joined, total)} <b>{joined}/{total}</b>\n"
            + LINE
            + "\nAfter joining, tap <b>✅ I Have Joined</b>."
        )
    rows = []
    for ch in missing:
        if ch["link"]:
            rows.append([InlineKeyboardButton(f"📢 Join Channel {ch['n']}  ↗", url=ch["link"])])
    rows.append([InlineKeyboardButton("✅ I Have Joined", callback_data="recheck")])
    return text, InlineKeyboardMarkup(rows)


# ----------------------------------------------------------------------------
# INDEXING (file name + file_id are saved in the database)
# ----------------------------------------------------------------------------
async def index_message(m: Message) -> bool:
    media = m.document or m.video or m.audio
    if not media:
        return False
    caption = m.caption or ""
    title = getattr(media, "file_name", None) or caption or f"file_{m.id}"
    await store.upsert_file(
        m.id, title, norm(f"{title} {caption}"), media.file_size or 0, media.file_id, caption
    )
    log.info("Indexed: %s", title)
    return True


# Any new file posted in the DB channel is indexed automatically
@app.on_message(filters.chat(DB_CHANNEL) & (filters.document | filters.video | filters.audio))
async def index_file(_, m: Message):
    await index_message(m)


# ----------------------------------------------------------------------------
# AUTO FORWARD: new messages from SOURCE_GROUPS -> DB_CHANNEL (and indexed instantly)
# ----------------------------------------------------------------------------
if SOURCE_GROUPS:

    @app.on_message(filters.chat(SOURCE_GROUPS) & ~filters.service)
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
        tmp = await app.send_message(DB_CHANNEL, "🔄 indexing...", disable_notification=True)
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
# USER COMMANDS
# ----------------------------------------------------------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, m: Message):
    await store.add_user(m.from_user.id)
    missing = await not_joined(client, m.from_user.id)
    if missing:
        text, kb = await join_view(missing)
        return await m.reply(text, reply_markup=kb, quote=True)
    await send_welcome(m)


@app.on_message(filters.command("help") & filters.private)
async def help_cmd(_, m: Message):
    await m.reply(help_text(is_admin_id(m.from_user.id)), reply_markup=back_keyboard(), quote=True)


# ----------------------------------------------------------------------------
# ADMIN COMMANDS
# ----------------------------------------------------------------------------
@app.on_message(filters.command("stats") & filters.private & filters.user(ADMINS))
async def stats_cmd(_, m: Message):
    files = await store.count_files()
    users = await store.count_users()
    channels = len(await get_force_channels())
    kind = "MongoDB ✅ (permanent)" if store.persistent else "SQLite ⚠️ (may be lost on restart)"
    await m.reply(
        "📊 <b>Bot Statistics</b>\n"
        + LINE
        + f"\n🎬 Files: <b>{files}</b>\n"
        f"👥 Users: <b>{users}</b>\n"
        f"📢 Force-join channels: <b>{channels}</b>\n"
        f"🔗 Auto-forward groups: <b>{len(SOURCE_GROUPS)}</b>\n"
        f"⏳ Auto-delete: <b>{minutes() if AUTO_DELETE_SECONDS > 0 else 'off'}"
        f"{' min' if AUTO_DELETE_SECONDS > 0 else ''}</b>\n"
        f"💾 Database: {kind}\n"
        f"⏱ Uptime: <b>{fmt_uptime(time.time() - START_TIME)}</b>\n"
        + LINE,
        quote=True,
    )


@app.on_message(filters.command("broadcast") & filters.private & filters.user(ADMINS))
async def broadcast_cmd(client: Client, m: Message):
    src = m.reply_to_message
    text = m.text.split(None, 1)[1] if len(m.command) > 1 else None
    if not src and not text:
        return await m.reply(
            "📢 <b>Broadcast</b>\n"
            + LINE
            + "\n<b>Reply</b> to a message with <code>/broadcast</code>,\n"
            "or directly: <code>/broadcast your message</code>",
            quote=True,
        )

    async def send_one(uid: int):
        if src:
            await src.copy(uid)
        else:
            await client.send_message(uid, text, disable_web_page_preview=True)

    user_ids = await store.all_user_ids()
    total = len(user_ids)
    status = await m.reply(f"📢 Starting broadcast... <b>{total}</b> users", quote=True)
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
        except Exception:
            fail += 1

        if time.time() - last_edit > 3:
            last_edit = time.time()
            try:
                await status.edit_text(
                    f"📢 Broadcast in progress...\n{progress_bar(i, total)} <b>{i}/{total}</b>"
                )
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await status.edit_text(
        "✅ <b>Broadcast Complete</b>\n"
        + LINE
        + f"\n📨 Sent: <b>{ok}</b>\n"
        f"🚫 Blocked/Deleted (removed from list): <b>{blocked}</b>\n"
        f"⚠️ Failed: <b>{fail}</b>"
    )


@app.on_message(filters.command("index") & filters.private & filters.user(ADMINS))
async def index_cmd(_, m: Message):
    full = len(m.command) > 1 and m.command[1].lower() == "full"
    status = await m.reply("⏳ Scanning the DB channel, please wait...", quote=True)
    last_edit = [0.0]

    async def progress(done, total, found):
        if time.time() - last_edit[0] < 3:
            return
        last_edit[0] = time.time()
        try:
            await status.edit_text(
                f"⏳ Scan in progress...\n{progress_bar(done, total)} <b>{done}/{total}</b>\n"
                f"🎬 Files found: <b>{found}</b>"
            )
        except Exception:
            pass

    try:
        found, last_id = await scan_db_channel(full=full, progress=progress)
    except Exception as e:
        return await status.edit_text(
            f"❌ <b>Scan failed</b>\n{esc(e)}\n\nIs the bot an admin in the DB channel and able to post? Please check."
        )
    total = await store.count_files()
    await status.edit_text(
        "✅ <b>Scan Complete</b>\n"
        + LINE
        + f"\n📥 Found this time: <b>{found}</b> files\n"
        f"🎬 Total indexed: <b>{total}</b>\n"
        f"🆔 Last message id: <code>{last_id}</code>"
    )


ADDCHANNEL_USAGE = (
    "➕ <b>Add Force-Join Channel</b>\n"
    + LINE
    + "\n<code>/addchannel 1 @username</code>\n"
    "<code>/addchannel 2 -1001234567890</code>\n"
    "<code>/addchannel 3 -1001234567890 https://t.me/+InviteLink</code>\n"
    "<code>/addchannel @username</code> (goes into an empty slot automatically)\n\n"
    "Slots 1 to 10. Using the same slot again replaces the old channel.\n"
    "The bot must be an <b>admin</b> in that channel."
)


@app.on_message(filters.command("addchannel") & filters.private & filters.user(ADMINS))
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
                "⚠️ All 10 slots are full. Give a slot number to replace one, or use /delchannel.",
                quote=True,
            )
        rest = args
    if not 1 <= slot <= 10:
        return await m.reply("⚠️ Slot must be between 1 and 10.", quote=True)

    ref = parse_chat(rest[0])
    link = rest[1] if len(rest) > 1 else ""

    try:
        chat = await client.get_chat(ref)
    except Exception as e:
        return await m.reply(
            f"❌ <b>Channel not found</b>\n{esc(e)}\n\nFirst make the bot an <b>admin</b> in that channel, then run the command again.",
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
        note += "\n⚠️ The bot doesn't appear to be an admin in this channel. The join check will only work once it is."
    if not link:
        note += "\n⚠️ This is a private channel and no link was found. Add an invite link at the end of the command."
    await m.reply(
        "✅ <b>Channel Added</b>\n"
        + LINE
        + f"\n📌 Slot: <b>{slot}</b>\n"
        f"📢 Name: <b>{esc(chat.title)}</b>\n"
        f"🆔 ID: <code>{chat.id}</code>\n"
        f"🔗 Link: {esc(link) or 'none'}{note}",
        quote=True,
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("delchannel") & filters.private & filters.user(ADMINS))
async def delchannel_cmd(_, m: Message):
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await m.reply("Usage: <code>/delchannel 1</code>", quote=True)
    slot = int(m.command[1])
    await store.del_channel(slot)
    if any(c["n"] == slot for c in ENV_CHANNELS):
        await store.set_channel(slot, "", "")  # disable the slot that comes from env
    await m.reply(f"🗑 Slot <b>{slot}</b> removed.", quote=True)


@app.on_message(filters.command("channels") & filters.private & filters.user(ADMINS))
async def channels_cmd(client: Client, m: Message):
    chans = await get_force_channels()
    if not chans:
        return await m.reply("📭 No force-join channels are set. Use /addchannel.", quote=True)

    blocks = []
    for c in chans:
        title, bot_ok = "❓ Not found", False
        try:
            chat = await client.get_chat(c["ref"])
            title = chat.title
            me = await client.get_chat_member(chat.id, "me")
            bot_ok = me.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
        except Exception:
            pass
        blocks.append(
            f"<b>{c['n']}. {esc(title)}</b>\n"
            f"🆔 <code>{c['ref']}</code>\n"
            f"🔗 {esc(c['link']) or 'no link'}\n"
            f"🛡 Bot: {'✅ Admin' if bot_ok else '⚠️ Not admin'}"
        )
    await m.reply(
        "📢 <b>Force-Join Channels</b>\n" + LINE + "\n" + "\n\n".join(blocks),
        quote=True,
        disable_web_page_preview=True,
    )


# ----------------------------------------------------------------------------
# SEARCH
# ----------------------------------------------------------------------------
_search_cache: dict = {}


def cache_query(token: str, query: str):
    _search_cache[token] = query
    while len(_search_cache) > 500:
        _search_cache.pop(next(iter(_search_cache)))


async def run_search(query: str):
    """(results, fuzzy). If there's no exact match, similar results (at least one word) are returned."""
    words = norm(query).split()
    results = await store.find(words)
    if results or len(words) < 2:
        return results, False
    useful = [w for w in words if len(w) >= 3] or words
    return await store.find_any(useful), True


async def build_page(query: str, page: int, token: str):
    results, fuzzy = await run_search(query)
    if not results:
        return None, None

    total = len(results)
    pages = max(math.ceil(total / RESULTS_PER_PAGE), 1)
    page = min(max(page, 0), pages - 1)
    chunk = results[page * RESULTS_PER_PAGE:(page + 1) * RESULTS_PER_PAGE]

    text = (
        "🔎 <b>Search Results</b>\n"
        + LINE
        + f"\n📝 Query: <i>{esc(query[:60])}</i>\n"
        f"📦 Found: <b>{total}</b>  •  Page <b>{page + 1}/{pages}</b>\n"
    )
    if fuzzy:
        text += "🔀 <i>No exact match found, showing similar results</i>\n"
    text += LINE + "\n👇 <b>Choose your file</b>"

    rows = [
        [
            InlineKeyboardButton(
                f"{file_icon(title)} {human(size)} ┃ {title[:38]}",
                callback_data=f"get|{mid}",
            )
        ]
        for mid, title, size in chunk
    ]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("« Prev", callback_data=f"pg|{page - 1}|{token}"))
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"pg|{page + 1}|{token}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton("× Close ×", callback_data="close")])
    return text, InlineKeyboardMarkup(rows)


NOT_FOUND_TEXT = (
    "😕 <b>Nothing Found</b>\n"
    + LINE
    + "\n🔎 <i>{query}</i>\n\n"
    "💡 <b>Try this:</b>\n"
    "• Check the spelling\n"
    "• Use a shorter name (just the main word)\n"
    "• Try both Hindi and English\n"
    + LINE
)


@app.on_message(
    filters.text
    & filters.private
    & ~filters.command(
        ["start", "help", "stats", "broadcast", "addchannel", "delchannel", "channels", "index"]
    )
)
async def search_handler(client: Client, m: Message):
    await store.add_user(m.from_user.id)
    missing = await not_joined(client, m.from_user.id)
    if missing:
        text, kb = await join_view(missing)
        return await m.reply(text, reply_markup=kb, quote=True)

    try:
        await client.send_chat_action(m.chat.id, enums.ChatAction.TYPING)
    except Exception:
        pass

    query = m.text[:100]
    token = f"{m.from_user.id}{m.id}"
    cache_query(token, query)
    text, kb = await build_page(query, 0, token)

    if not text:
        rows = []
        if SUPPORT_USERNAME:
            rows.append([InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_USERNAME}")])
        rows.append([InlineKeyboardButton("× Close ×", callback_data="close")])
        reply = await m.reply(
            NOT_FOUND_TEXT.format(query=esc(query[:60])),
            reply_markup=InlineKeyboardMarkup(rows),
            quote=True,
        )
        schedule_delete(reply, m)
        return

    reply = await m.reply(text, reply_markup=kb, quote=True)
    schedule_delete(reply, m)


# ----------------------------------------------------------------------------
# CALLBACKS
# ----------------------------------------------------------------------------
@app.on_callback_query(filters.regex(r"^recheck$"))
async def recheck_cb(client: Client, cq: CallbackQuery):
    missing = await not_joined(client, cq.from_user.id)
    if missing:
        await cq.answer("You haven't joined all the channels yet!", show_alert=True)
        text, kb = await join_view(missing)
        await edit(cq.message, text, kb)
        return
    await cq.answer("🎉 Thank you! Now send the name of a Movie/Series.")
    await edit(cq.message, welcome_text(cq.from_user), home_keyboard())


@app.on_callback_query(filters.regex(r"^home$"))
async def home_cb(_, cq: CallbackQuery):
    await edit(cq.message, welcome_text(cq.from_user), home_keyboard())
    await cq.answer()


@app.on_callback_query(filters.regex(r"^help$"))
async def help_cb(_, cq: CallbackQuery):
    await edit(cq.message, help_text(is_admin_id(cq.from_user.id)), back_keyboard())
    await cq.answer()


@app.on_callback_query(filters.regex(r"^about$"))
async def about_cb(_, cq: CallbackQuery):
    await edit(cq.message, await about_text(), back_keyboard())
    await cq.answer()


@app.on_callback_query(filters.regex(r"^noop$"))
async def noop_cb(_, cq: CallbackQuery):
    await cq.answer()


@app.on_callback_query(filters.regex(r"^close$"))
async def close_cb(_, cq: CallbackQuery):
    try:
        await cq.message.delete()
    except Exception:
        await cq.answer("Couldn't close this.", show_alert=True)
        return
    await cq.answer()


@app.on_callback_query(filters.regex(r"^pg\|"))
async def page_cb(client: Client, cq: CallbackQuery):
    _, page, token = cq.data.split("|", 2)
    query = _search_cache.get(token)
    if not query:
        return await cq.answer("This search has expired, please send the name again.", show_alert=True)
    text, kb = await build_page(query, int(page), token)
    if text:
        await edit(cq.message, text, kb)
    await cq.answer()


def file_caption(title: str, size: int) -> str:
    text = (
        f"{file_icon(title)} <b>{esc(title[:200])}</b>\n"
        + LINE
        + f"\n💾 Size: <b>{human(size)}</b>\n"
    )
    if AUTO_DELETE_SECONDS > 0:
        text += f"⏳ Auto-delete: <b>{minutes()} min</b>\n"
    text += LINE + "\n✅ <i>Save or forward it now</i>"
    if BOT_USERNAME:
        text += f"\n🤖 @{BOT_USERNAME}"
    return text[:1024]


@app.on_callback_query(filters.regex(r"^get\|"))
async def get_cb(client: Client, cq: CallbackQuery):
    missing = await not_joined(client, cq.from_user.id)
    if missing:
        await cq.answer("Please join all the channels first!", show_alert=True)
        text, kb = await join_view(missing)
        return await client.send_message(cq.from_user.id, text, reply_markup=kb)

    msg_id = int(cq.data.split("|")[1])
    row = await store.get_file(msg_id)
    title = (row or {}).get("title") or f"file_{msg_id}"
    caption = file_caption(title, (row or {}).get("size", 0))
    kb = file_keyboard()
    sent = None

    # 1) Send using the file_id saved in the database (works even after a restart)
    if row and row.get("file_id"):
        try:
            sent = await client.send_cached_media(
                cq.from_user.id, row["file_id"], caption=caption, reply_markup=kb
            )
        except Exception as e:
            log.warning("Could not send via file_id (%s), trying to copy from the channel", e)

    # 2) Fallback: copy from the DB channel
    if not sent:
        try:
            sent = await client.copy_message(
                cq.from_user.id, DB_CHANNEL, msg_id, caption=caption, reply_markup=kb
            )
        except Exception as e:
            log.error("Error while sending file: %s", e)
            return await cq.answer("Couldn't get the file, please try again later.", show_alert=True)

    await cq.answer("📥 File sent ✅")
    schedule_delete(sent)


# ----------------------------------------------------------------------------
# START
# ----------------------------------------------------------------------------
async def notify_admins(text: str):
    for admin in ADMINS[:5]:
        try:
            await app.send_message(admin, text)
        except Exception:
            pass


async def _startup_scan():
    try:
        found, last_id = await scan_db_channel(full=False)
        total = await store.count_files()
        text = (
            "✅ <b>Bot Started</b>\n"
            + LINE
            + f"\n📥 New files indexed: <b>{found}</b>\n"
            f"🎬 Total files in database: <b>{total}</b>"
        )
        if not store.persistent:
            text += "\n⚠️ MONGO_URI is not set, data may be lost on restart."
        log.info("Startup index: %s new files, total %s", found, total)
    except Exception as e:
        text = (
            f"❌ <b>Startup index failed</b>\n{esc(e)}\n\n"
            "Make the bot an admin in the DB channel, then run /index full."
        )
        log.error("Startup index failed: %s", e)
    await notify_admins(text)


async def set_menu_commands():
    """Commands shown in Telegram's command menu (when you tap /)."""
    user_cmds = [
        BotCommand("start", "🏠 Start the bot"),
        BotCommand("help", "📖 How to use"),
    ]
    admin_cmds = user_cmds + [
        BotCommand("stats", "📊 Bot statistics"),
        BotCommand("broadcast", "📢 Message everyone"),
        BotCommand("index", "🗂 Index the DB channel"),
        BotCommand("addchannel", "➕ Add force-join channel"),
        BotCommand("delchannel", "🗑 Remove a channel"),
        BotCommand("channels", "📋 List channels"),
    ]
    try:
        await app.set_bot_commands(user_cmds)
        for admin in ADMINS:
            try:
                await app.set_bot_commands(admin_cmds, scope=BotCommandScopeChat(admin))
            except Exception:
                pass  # may fail if the admin hasn't started the bot yet
    except Exception as e:
        log.warning("Could not set command menu: %s", e)


async def main():
    global BOT_USERNAME
    await store.init()
    await app.start()
    BOT_USERNAME = (await app.get_me()).username or ""
    log.info("Bot started: @%s", BOT_USERNAME)
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
