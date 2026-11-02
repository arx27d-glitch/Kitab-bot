import asyncio
import logging
import os
import re
import sqlite3

from dotenv import load_dotenv
from pyrogram import Client, enums, filters
from pyrogram.errors import FloodWait, RPCError, UserNotParticipant
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bookbot")


# ----------------------------------------------------------------------------
# CONFIG (sab kuch environment variables se aata hai, .env.example dekho)
# ----------------------------------------------------------------------------
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


API_ID = int(env("API_ID", "0"))
API_HASH = env("API_HASH")
BOT_TOKEN = env("BOT_TOKEN")
DB_CHANNEL = int(env("DB_CHANNEL", "0"))
ADMINS = [int(x) for x in env("ADMINS").replace(",", " ").split() if x.lstrip("-").isdigit()]

BOT_NAME = env("BOT_NAME", "Kitab Bot")
OWNER_USERNAME = env("OWNER_USERNAME").lstrip("@")
SUPPORT_USERNAME = env("SUPPORT_USERNAME").lstrip("@")
UPDATES_CHANNEL = env("UPDATES_CHANNEL").lstrip("@")

AUTO_DELETE_SECONDS = int(env("AUTO_DELETE_SECONDS", "300"))  # 300 = 5 minute, 0 = off
RESULTS_PER_PAGE = int(env("RESULTS_PER_PAGE", "8"))
DB_PATH = env("DB_PATH", "files.db")

START_TEXT = env(
    "START_TEXT",
    "Namaste {mention}! 👋\n\n"
    "Main <b>{bot_name}</b> hu. Jis kitab ki file chahiye uska <b>naam</b> bhejo, "
    "main dhoondh kar bhej dunga.\n\n"
    "⏳ Files {minutes} minute baad auto-delete ho jati hain, isliye save kar lena.",
).replace("\\n", "\n")

JOIN_TEXT = env(
    "JOIN_TEXT",
    "⚠️ Bot use karne ke liye pehle neeche diye gaye saare channels join karo, "
    "phir <b>✅ Maine Join Kar Liya</b> dabao.",
).replace("\\n", "\n")


def parse_chat(value: str):
    value = value.strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value.lstrip("@")


def load_force_channels():
    """CHANNEL_1 ... CHANNEL_4 (aur zarurat ho to CHANNEL_5...) padhta hai.

    CHANNEL_n      = @username  ya  -100xxxxxxxxxx (numeric id)
    CHANNEL_n_LINK = invite link (private channel ke liye zaroori, public ke liye optional)
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
            log.warning("CHANNEL_%s private hai, CHANNEL_%s_LINK bhi set karo.", i, i)
        channels.append({"n": i, "ref": ref, "link": link})
    return channels


FORCE_CHANNELS = load_force_channels()

if not (API_ID and API_HASH and BOT_TOKEN and DB_CHANNEL):
    raise SystemExit("API_ID, API_HASH, BOT_TOKEN aur DB_CHANNEL set karna zaroori hai (.env dekho).")

app = Client("bookbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ----------------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------------
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute(
    """CREATE TABLE IF NOT EXISTS files(
        msg_id INTEGER PRIMARY KEY, title TEXT, search TEXT, size INTEGER)"""
)
db.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY)")
db.commit()


def norm(text: str) -> str:
    return re.sub(r"[._\-\[\]\(\)]+", " ", text or "").lower().strip()


def human(size: int) -> str:
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def add_user(user_id: int):
    db.execute("INSERT OR IGNORE INTO users VALUES(?)", (user_id,))
    db.commit()


def find(query: str):
    words = norm(query).split()
    if not words:
        return []
    sql = "SELECT msg_id, title, size FROM files WHERE " + " AND ".join(["search LIKE ?"] * len(words))
    return db.execute(sql + " ORDER BY title", [f"%{w}%" for w in words]).fetchall()


# ----------------------------------------------------------------------------
# AUTO DELETE
# ----------------------------------------------------------------------------
_tasks = set()


def schedule_delete(*messages: Message, delay: int = AUTO_DELETE_SECONDS):
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


# ----------------------------------------------------------------------------
# FORCE JOIN
# ----------------------------------------------------------------------------
async def not_joined(client: Client, user_id: int):
    missing = []
    for ch in FORCE_CHANNELS:
        try:
            member = await client.get_chat_member(ch["ref"], user_id)
            if member.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
                missing.append(ch)
        except UserNotParticipant:
            missing.append(ch)
        except RPCError as e:
            # Bot channel me admin nahi hai ya channel galat hai: user ko block mat karo
            log.error("Channel %s check nahi hua (%s). Bot ko us channel me admin banao.", ch["ref"], e)
    return missing


def join_keyboard(missing):
    rows = []
    for ch in missing:
        if ch["link"]:
            rows.append([InlineKeyboardButton(f"📢 Join Channel {ch['n']}", url=ch["link"])])
    rows.append([InlineKeyboardButton("✅ Maine Join Kar Liya", callback_data="recheck")])
    return InlineKeyboardMarkup(rows)


def welcome_keyboard():
    rows = []
    row = []
    if UPDATES_CHANNEL:
        row.append(InlineKeyboardButton("📢 Updates", url=f"https://t.me/{UPDATES_CHANNEL}"))
    if SUPPORT_USERNAME:
        row.append(InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_USERNAME}"))
    if row:
        rows.append(row)
    if OWNER_USERNAME:
        rows.append([InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}")])
    return InlineKeyboardMarkup(rows) if rows else None


def welcome_text(user) -> str:
    return START_TEXT.format(
        mention=user.mention,
        first_name=user.first_name,
        bot_name=BOT_NAME,
        minutes=max(AUTO_DELETE_SECONDS // 60, 1),
    )


# ----------------------------------------------------------------------------
# INDEXING (DB channel me jo file aayegi wo search me aa jayegi)
# ----------------------------------------------------------------------------
@app.on_message(filters.chat(DB_CHANNEL) & (filters.document | filters.video | filters.audio))
async def index_file(_, m: Message):
    media = m.document or m.video or m.audio
    title = getattr(media, "file_name", None) or m.caption or f"file_{m.id}"
    db.execute(
        "INSERT OR REPLACE INTO files VALUES(?,?,?,?)",
        (m.id, title, norm(f"{title} {m.caption or ''}"), media.file_size or 0),
    )
    db.commit()
    log.info("Indexed: %s", title)


# ----------------------------------------------------------------------------
# COMMANDS
# ----------------------------------------------------------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, m: Message):
    add_user(m.from_user.id)
    missing = await not_joined(client, m.from_user.id)
    if missing:
        return await m.reply(JOIN_TEXT, reply_markup=join_keyboard(missing), quote=True)
    await m.reply(welcome_text(m.from_user), reply_markup=welcome_keyboard(), quote=True)


@app.on_message(filters.command("help") & filters.private)
async def help_cmd(_, m: Message):
    await m.reply("Kitab ka naam (ya uska kuch hissa) bhejo, main file dhoond dunga.", quote=True)


@app.on_message(filters.command("stats") & filters.private & filters.user(ADMINS))
async def stats_cmd(_, m: Message):
    files = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    await m.reply(f"📊 Files: <b>{files}</b>\n👥 Users: <b>{users}</b>", parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command("broadcast") & filters.private & filters.user(ADMINS))
async def broadcast_cmd(client: Client, m: Message):
    if not m.reply_to_message:
        return await m.reply("Jis message ko bhejna hai uspe reply karke /broadcast likho.")
    user_ids = [r[0] for r in db.execute("SELECT user_id FROM users").fetchall()]
    ok = fail = 0
    status = await m.reply(f"Broadcast shuru... ({len(user_ids)} users)")
    for uid in user_ids:
        try:
            await m.reply_to_message.copy(uid)
            ok += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await m.reply_to_message.copy(uid)
                ok += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Broadcast khatam\nSuccess: {ok}\nFailed: {fail}")


# ----------------------------------------------------------------------------
# SEARCH
# ----------------------------------------------------------------------------
_search_cache: dict = {}


def cache_query(token: str, query: str):
    _search_cache[token] = query
    while len(_search_cache) > 500:
        _search_cache.pop(next(iter(_search_cache)))


def build_page(query: str, page: int, token: str):
    results = find(query)
    if not results:
        return None, None
    total = len(results)
    chunk = results[page * RESULTS_PER_PAGE:(page + 1) * RESULTS_PER_PAGE]
    rows = [
        [InlineKeyboardButton(f"[{human(size)}] {title[:50]}", callback_data=f"get|{mid}")]
        for mid, title, size in chunk
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pg|{page - 1}|{token}"))
    if (page + 1) * RESULTS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"pg|{page + 1}|{token}"))
    if nav:
        rows.append(nav)
    return f"🔎 <b>{total}</b> result mile: <i>{query[:60]}</i>", InlineKeyboardMarkup(rows)


@app.on_message(
    filters.text & filters.private & ~filters.command(["start", "help", "stats", "broadcast"])
)
async def search_handler(client: Client, m: Message):
    add_user(m.from_user.id)
    missing = await not_joined(client, m.from_user.id)
    if missing:
        return await m.reply(JOIN_TEXT, reply_markup=join_keyboard(missing), quote=True)

    token = f"{m.from_user.id}{m.id}"
    cache_query(token, m.text)
    text, kb = build_page(m.text, 0, token)
    if not text:
        reply = await m.reply("😕 Kuch nahi mila. Spelling check karke ya chhota naam likh kar try karo.", quote=True)
        schedule_delete(reply, m)
        return
    reply = await m.reply(text, reply_markup=kb, quote=True, parse_mode=enums.ParseMode.HTML)
    schedule_delete(reply, m)


# ----------------------------------------------------------------------------
# CALLBACKS
# ----------------------------------------------------------------------------
@app.on_callback_query(filters.regex(r"^recheck$"))
async def recheck_cb(client: Client, cq: CallbackQuery):
    missing = await not_joined(client, cq.from_user.id)
    if missing:
        await cq.answer("Abhi bhi saare channels join nahi kiye!", show_alert=True)
        try:
            await cq.message.edit_reply_markup(join_keyboard(missing))
        except Exception:
            pass
        return
    await cq.answer("Shukriya! Ab kitab ka naam bhejo.")
    await cq.message.edit_text(welcome_text(cq.from_user), reply_markup=welcome_keyboard())


@app.on_callback_query(filters.regex(r"^pg\|"))
async def page_cb(client: Client, cq: CallbackQuery):
    _, page, token = cq.data.split("|", 2)
    query = _search_cache.get(token)
    if not query:
        return await cq.answer("Ye search purani ho gayi, dobara naam bhejo.", show_alert=True)
    text, kb = build_page(query, int(page), token)
    if text:
        await cq.message.edit_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^get\|"))
async def get_cb(client: Client, cq: CallbackQuery):
    missing = await not_joined(client, cq.from_user.id)
    if missing:
        await cq.answer("Pehle saare channels join karo!", show_alert=True)
        return await client.send_message(
            cq.from_user.id, JOIN_TEXT, reply_markup=join_keyboard(missing)
        )

    msg_id = int(cq.data.split("|")[1])
    try:
        sent = await client.copy_message(cq.from_user.id, DB_CHANNEL, msg_id)
    except Exception as e:
        log.error("File bhejne me error: %s", e)
        return await cq.answer("File nahi mil payi, baad me try karo.", show_alert=True)

    await cq.answer("File bhej di ✅")
    if AUTO_DELETE_SECONDS > 0:
        mins = max(AUTO_DELETE_SECONDS // 60, 1)
        notice = await client.send_message(
            cq.from_user.id,
            f"⏳ Ye file <b>{mins} minute</b> me auto-delete ho jayegi. Abhi save ya forward kar lo.",
            parse_mode=enums.ParseMode.HTML,
            reply_to_message_id=sent.id,
        )
        schedule_delete(sent, notice)


if __name__ == "__main__":
    log.info("Bot start ho raha hai... Force-join channels: %s", [c["ref"] for c in FORCE_CHANNELS])
    app.run()
