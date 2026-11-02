import asyncio
import logging
import os
import re
import sqlite3

from dotenv import load_dotenv
from pyrogram import Client, enums, filters, idle
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
# CONFIG
# ----------------------------------------------------------------------------
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


API_ID = int(env("API_ID", "0"))
API_HASH = env("API_HASH")
BOT_TOKEN = env("BOT_TOKEN")
DB_CHANNEL = int(env("DB_CHANNEL", "0"))
ADMINS = [int(x) for x in env("ADMINS").replace(",", " ").split() if x.lstrip("-").isdigit()]

SOURCE_GROUPS = [int(x) for x in env("SOURCE_GROUPS").replace(",", " ").split() if x.lstrip("-").isdigit()]
FORWARD_ALL = env("FORWARD_ALL", "false").lower() in ("1", "true", "yes")
AUTO_INDEX_ON_START = env("AUTO_INDEX_ON_START", "true").lower() in ("1", "true", "yes")

BOT_NAME = env("BOT_NAME", "Kitab Bot")
OWNER_USERNAME = env("OWNER_USERNAME").lstrip("@")
SUPPORT_USERNAME = env("SUPPORT_USERNAME").lstrip("@")
UPDATES_CHANNEL = env("UPDATES_CHANNEL").lstrip("@")

AUTO_DELETE_SECONDS = int(env("AUTO_DELETE_SECONDS", "300"))
RESULTS_PER_PAGE = int(env("RESULTS_PER_PAGE", "8"))
DB_PATH = env("DB_PATH", "files.db")

START_TEXT = env(
    "START_TEXT",
    "Namaste {mention}! 👋\n\n"
    "Main <b>{bot_name}</b> hu. Jis Movie ki file chahiye uska <b>naam</b> bhejo, "
    "main dhoondh kar bhej dunga.\n\n"
    "⏳ Files {minutes} minute baad auto-delete ho jati hain, isliye save kar lena.",
).replace("\\n", "\n")

JOIN_TEXT = env(
    "JOIN_TEXT",
    "⚠️ Bot use karne ke liye neeche diye gaye <b>saare channels</b> join karo.\n\n"
    "Public aur Private dono channels ho sakte hain. Sabhi configured channels join karna zaroori hai.\n"
    "Private channel mein join request bheji hai to admin ke approve karne ka wait karo.\n\n"
    "Sab join/approve hone ke baad <b>✅ Maine Join Kar Liya</b> button dabao.",
).replace("\\n", "\n")


def parse_chat(value: str):
    value = value.strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value.lstrip("@")


def load_force_channels():
    """CHANNEL_1 se CHANNEL_50 tak public/private channels load karta hai."""
    channels = []

    for i in range(1, 51):
        raw = env(f"CHANNEL_{i}")
        if not raw:
            continue

        ref = parse_chat(raw)
        link = env(f"CHANNEL_{i}_LINK")

        if not link and isinstance(ref, str):
            link = f"https://t.me/{ref}"

        if not link:
            log.warning(
                "CHANNEL_%s ka invite link set nahi hai. Private channel ke liye link zaroori hai.",
                i,
            )

        channels.append({"n": i, "ref": ref, "link": link})

    return channels


ENV_CHANNELS = load_force_channels()

if not (API_ID and API_HASH and BOT_TOKEN and DB_CHANNEL):
    raise SystemExit("API_ID, API_HASH, BOT_TOKEN aur DB_CHANNEL set karna zaroori hai.")

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
db.execute("CREATE TABLE IF NOT EXISTS forwarded(uid TEXT PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS channels(slot INTEGER PRIMARY KEY, ref TEXT, link TEXT)")
db.commit()


def get_meta(key: str, default: str = "") -> str:
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(key: str, value: str):
    db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))
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
    sql = "SELECT msg_id, title, size FROM files WHERE " + " AND ".join(
        ["search LIKE ?"] * len(words)
    )
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
def get_force_channels():
    """Combine Railway ENV channels and /addchannel entries.

    Both sources are active together. Duplicate channel IDs are shown only once.
    ENV slots and database slots are independent; /addchannel never replaces an
    ENV channel just because the slot number is the same.
    """
    combined = []
    seen = set()

    for ch in ENV_CHANNELS:
        key = str(ch["ref"]).lower()
        if key not in seen:
            combined.append(dict(ch))
            seen.add(key)

    rows = db.execute(
        "SELECT slot, ref, link FROM channels WHERE ref != '' ORDER BY slot"
    ).fetchall()

    for slot, ref, link in rows:
        parsed_ref = parse_chat(ref)
        key = str(parsed_ref).lower()
        if key in seen:
            continue
        combined.append({"n": slot, "ref": parsed_ref, "link": link})
        seen.add(key)

    # Display numbering is sequential, so ENV and DB slot overlaps are clear.
    for index, channel in enumerate(combined, start=1):
        channel["n"] = index

    return combined


async def not_joined(client: Client, user_id: int):
    """Return missing channels; return None if membership could not be verified."""
    missing = []

    for ch in get_force_channels():
        try:
            member = await client.get_chat_member(ch["ref"], user_id)
            if member.status in (
                enums.ChatMemberStatus.LEFT,
                enums.ChatMemberStatus.BANNED,
            ):
                missing.append(ch)

        except UserNotParticipant:
            missing.append(ch)

        except RPCError as e:
            # A permissions/invalid-channel error is NOT proof that the user
            # has not joined. Tell the user/admin to fix bot channel access.
            log.error(
                "Membership check failed for channel %s: %s. "
                "Make the bot admin and verify the channel ID.",
                ch["ref"], e,
            )
            return None

        except Exception as e:
            log.exception("Channel %s check failed: %s", ch["ref"], e)
            return None

    return missing


def join_keyboard(missing):
    """Har pending channel ka alag Join button dikhata hai."""
    rows = []

    for ch in missing:
        if ch["link"]:
            rows.append([
                InlineKeyboardButton(
                    f"📢 Join Channel {ch['n']}",
                    url=ch["link"],
                )
            ])

    rows.append([
        InlineKeyboardButton(
            "✅ Maine Join Kar Liya",
            callback_data="recheck",
        )
    ])

    return InlineKeyboardMarkup(rows)


def welcome_keyboard():
    rows = []
    row = []

    if UPDATES_CHANNEL:
        row.append(
            InlineKeyboardButton(
                "📢 Updates",
                url=f"https://t.me/{UPDATES_CHANNEL}",
            )
        )

    if SUPPORT_USERNAME:
        row.append(
            InlineKeyboardButton(
                "💬 Support",
                url=f"https://t.me/{SUPPORT_USERNAME}",
            )
        )

    if row:
        rows.append(row)

    if OWNER_USERNAME:
        rows.append([
            InlineKeyboardButton(
                "👤 Owner",
                url=f"https://t.me/{OWNER_USERNAME}",
            )
        ])

    return InlineKeyboardMarkup(rows) if rows else None


def welcome_text(user) -> str:
    return START_TEXT.format(
        mention=user.mention,
        first_name=user.first_name,
        bot_name=BOT_NAME,
        minutes=max(AUTO_DELETE_SECONDS // 60, 1),
    )


# ----------------------------------------------------------------------------
# INDEXING
# ----------------------------------------------------------------------------
def index_message(m: Message):
    media = m.document or m.video or m.audio
    if not media:
        return

    title = getattr(media, "file_name", None) or m.caption or f"file_{m.id}"

    db.execute(
        "INSERT OR REPLACE INTO files VALUES(?,?,?,?)",
        (m.id, title, norm(f"{title} {m.caption or ''}"), media.file_size or 0),
    )
    db.commit()
    log.info("Indexed: %s", title)


@app.on_message(filters.chat(DB_CHANNEL) & (filters.document | filters.video | filters.audio))
async def index_file(_, m: Message):
    index_message(m)


# ----------------------------------------------------------------------------
# AUTO FORWARD
# ----------------------------------------------------------------------------
if SOURCE_GROUPS:

    @app.on_message(filters.chat(SOURCE_GROUPS) & ~filters.service)
    async def auto_forward(_, m: Message):
        media = m.document or m.video or m.audio

        if not media and not FORWARD_ALL:
            return

        uid = media.file_unique_id if media else None

        if uid and db.execute(
            "SELECT 1 FROM forwarded WHERE uid=?", (uid,)
        ).fetchone():
            return

        try:
            sent = await m.copy(DB_CHANNEL)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            sent = await m.copy(DB_CHANNEL)

        except Exception as e:
            log.error("Auto-forward fail (group %s): %s", m.chat.id, e)
            return

        if uid:
            db.execute("INSERT OR IGNORE INTO forwarded VALUES(?)", (uid,))
            db.commit()
            index_message(sent)


# ----------------------------------------------------------------------------
# COMMANDS
# ----------------------------------------------------------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, m: Message):
    add_user(m.from_user.id)

    missing = await not_joined(client, m.from_user.id)
    if missing is None:
        return await m.reply(
            "⚠️ Channel membership verify nahi ho pa raha. Admin se bot ko har force-join channel mein admin banwane aur CHANNEL ID/username check karwane ko kaho.",
            quote=True,
        )
    if missing:
        return await m.reply(
            JOIN_TEXT,
            reply_markup=join_keyboard(get_force_channels()),
            quote=True,
        )

    await m.reply(
        welcome_text(m.from_user),
        reply_markup=welcome_keyboard(),
        quote=True,
    )


@app.on_message(filters.command("help") & filters.private)
async def help_cmd(_, m: Message):
    await m.reply(
        "Kitab ka naam (ya uska kuch hissa) bhejo, main file dhoond dunga.",
        quote=True,
    )


@app.on_message(filters.command("stats") & filters.private & filters.user(ADMINS))
async def stats_cmd(_, m: Message):
    files = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    await m.reply(
        f"📊 Files: <b>{files}</b>\n👥 Users: <b>{users}</b>",
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command("broadcast") & filters.private & filters.user(ADMINS))
async def broadcast_cmd(client: Client, m: Message):
    if not m.reply_to_message:
        return await m.reply(
            "Jis message ko bhejna hai uspe reply karke /broadcast likho."
        )

    user_ids = [
        r[0] for r in db.execute("SELECT user_id FROM users").fetchall()
    ]

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

    await status.edit_text(
        f"✅ Broadcast khatam\nSuccess: {ok}\nFailed: {fail}"
    )


# ----------------------------------------------------------------------------
# INDEX OLD FILES
# ----------------------------------------------------------------------------
_scan_lock = asyncio.Lock()


async def scan_db_channel(full: bool = False):
    """Return (found, last_id). full=True means scan from message ID 1."""
    async with _scan_lock:
        try:
            tmp = await app.send_message(
                DB_CHANNEL,
                "🔄 indexing...",
                disable_notification=True,
            )
        except Exception as e:
            log.error(
                "DB channel me message nahi bhej paya (bot admin hai?): %s",
                e,
            )
            raise

        last_id = tmp.id

        try:
            await tmp.delete()
        except Exception:
            pass

        start = 1 if full else int(get_meta("last_scanned", "0")) + 1
        found = 0

        for first in range(start, last_id + 1, 200):
            ids = list(range(first, min(first + 200, last_id + 1)))

            try:
                msgs = await app.get_messages(DB_CHANNEL, ids)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                msgs = await app.get_messages(DB_CHANNEL, ids)

            for msg in msgs:
                if (
                    msg
                    and not msg.empty
                    and (msg.document or msg.video or msg.audio)
                ):
                    index_message(msg)
                    found += 1

            await asyncio.sleep(0.5)

        set_meta("last_scanned", str(last_id))
        log.info(
            "Scan khatam: %s files index hui (last id %s)",
            found,
            last_id,
        )

        return found, last_id


@app.on_message(filters.command("index") & filters.private & filters.user(ADMINS))
async def index_cmd(_, m: Message):
    full = len(m.command) > 1 and m.command[1].lower() == "full"
    status = await m.reply("⏳ DB channel scan ho raha hai, thoda wait karo...")

    try:
        found, last_id = await scan_db_channel(full=full)

    except Exception as e:
        return await status.edit_text(
            f"❌ Scan fail: {e}\nBot DB channel me admin hai aur post kar sakta hai? Check karo."
        )

    total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    await status.edit_text(
        f"✅ Scan complete\nIs baar mili: <b>{found}</b> files\n"
        f"Total indexed: <b>{total}</b>\nLast message id: {last_id}",
        parse_mode=enums.ParseMode.HTML,
    )


# ----------------------------------------------------------------------------
# ADMIN: FORCE-JOIN CHANNEL ADD / REMOVE
# ----------------------------------------------------------------------------
ADDCHANNEL_USAGE = (
    "Use karo:\n"
    "<code>/addchannel 1 @username</code>\n"
    "<code>/addchannel 2 -1001234567890 https://t.me/+InviteLink</code>\n"
    "<code>/addchannel @username</code>\n\n"
    "Slot 1 se 50 tak support hai.\n"
    "Railway ke CHANNEL_1...CHANNEL_50 aur /addchannel dono ek saath kaam karte hain.\n"
    "Duplicate channel do baar count nahi hoga.\n"
    "Membership check ke liye bot ko har channel me admin banao."
)


@app.on_message(filters.command("addchannel") & filters.private & filters.user(ADMINS))
async def addchannel_cmd(client: Client, m: Message):
    args = m.command[1:]

    if not args:
        return await m.reply(
            ADDCHANNEL_USAGE,
            parse_mode=enums.ParseMode.HTML,
        )

    if re.fullmatch(r"\d{1,2}", args[0]) and len(args) >= 2:
        slot, rest = int(args[0]), args[1:]

    else:
        used = {row[0] for row in db.execute("SELECT slot FROM channels").fetchall()}
        slot = next((i for i in range(1, 51) if i not in used), None)

        if slot is None:
            return await m.reply(
                "Saare 50 slots bhar chuke hain. Slot number dekar replace karo ya /delchannel use karo."
            )

        rest = args

    if not 1 <= slot <= 50:
        return await m.reply(
            "Slot 1 se 50 ke beech hona chahiye."
        )

    ref = parse_chat(rest[0])
    link = rest[1] if len(rest) > 1 else ""

    try:
        chat = await client.get_chat(ref)

    except Exception as e:
        return await m.reply(
            f"❌ Channel nahi mila: {e}\n\n"
            "Pehle bot ko us channel me admin banao, phir command dobara chalao.",
            parse_mode=enums.ParseMode.HTML,
        )

    is_admin = False

    try:
        me = await client.get_chat_member(chat.id, "me")
        is_admin = me.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        )
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

    db.execute(
        "INSERT OR REPLACE INTO channels VALUES(?,?,?)",
        (slot, str(chat.id), link),
    )
    db.commit()

    note = ""

    if not is_admin:
        note += (
            "\n⚠️ Bot is channel me admin nahi dikh raha. "
            "Membership check ke liye bot ko admin banao."
        )

    if not link:
        note += (
            "\n⚠️ Join link nahi mila. Private channel ke liye invite link command me do."
        )

    await m.reply(
        f"✅ Slot <b>{slot}</b> me add ho gaya: <b>{chat.title}</b>\n"
        f"ID: <code>{chat.id}</code>\n"
        f"Link: {link or 'nahi'}{note}",
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("delchannel") & filters.private & filters.user(ADMINS))
async def delchannel_cmd(_, m: Message):
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await m.reply(
            "Use karo: <code>/delchannel 1</code>",
            parse_mode=enums.ParseMode.HTML,
        )

    slot = int(m.command[1])

    if not 1 <= slot <= 50:
        return await m.reply("Slot 1 se 50 ke beech hona chahiye.")

    db.execute("DELETE FROM channels WHERE slot=?", (slot,))

    db.commit()
    await m.reply(f"🗑 Slot {slot} hata diya.")


@app.on_message(filters.command("channels") & filters.private & filters.user(ADMINS))
async def channels_cmd(_, m: Message):
    chans = get_force_channels()

    if not chans:
        return await m.reply(
            "Koi force-join channel set nahi hai. /addchannel use karo."
        )

    lines = [
        f"{c['n']}. <code>{c['ref']}</code> - {c['link'] or 'link nahi'}"
        for c in chans
    ]

    await m.reply(
        "📢 Force-join channels:\n" + "\n".join(lines),
        parse_mode=enums.ParseMode.HTML,
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


def build_page(query: str, page: int, token: str):
    results = find(query)

    if not results:
        return None, None

    total = len(results)
    chunk = results[
        page * RESULTS_PER_PAGE:(page + 1) * RESULTS_PER_PAGE
    ]

    rows = [
        [
            InlineKeyboardButton(
                f"[{human(size)}] {title[:50]}",
                callback_data=f"get|{mid}",
            )
        ]
        for mid, title, size in chunk
    ]

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Prev",
                callback_data=f"pg|{page - 1}|{token}",
            )
        )

    if (page + 1) * RESULTS_PER_PAGE < total:
        nav.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"pg|{page + 1}|{token}",
            )
        )

    if nav:
        rows.append(nav)

    return (
        f"🔎 <b>{total}</b> result mile: <i>{query[:60]}</i>",
        InlineKeyboardMarkup(rows),
    )


@app.on_message(
    filters.text
    & filters.private
    & ~filters.command(
        [
            "start",
            "help",
            "stats",
            "broadcast",
            "addchannel",
            "delchannel",
            "channels",
            "index",
        ]
    )
)
async def search_handler(client: Client, m: Message):
    add_user(m.from_user.id)

    missing = await not_joined(client, m.from_user.id)

    if missing is None:
        return await m.reply(
            "⚠️ Channel membership verify nahi ho pa raha. Admin se bot ko har force-join channel mein admin banwane aur CHANNEL ID/username check karwane ko kaho.",
            quote=True,
        )

    if missing:
        return await m.reply(
            JOIN_TEXT,
            reply_markup=join_keyboard(get_force_channels()),
            quote=True,
        )

    token = f"{m.from_user.id}{m.id}"
    cache_query(token, m.text)

    text, kb = build_page(m.text, 0, token)

    if not text:
        reply = await m.reply(
            "😕 Kuch nahi mila. Spelling check karke ya chhota naam likh kar try karo.",
            quote=True,
        )
        schedule_delete(reply, m)
        return

    reply = await m.reply(
        text,
        reply_markup=kb,
        quote=True,
        parse_mode=enums.ParseMode.HTML,
    )
    schedule_delete(reply, m)


# ----------------------------------------------------------------------------
# CALLBACKS
# ----------------------------------------------------------------------------
@app.on_callback_query(filters.regex(r"^recheck$"))
async def recheck_cb(client: Client, cq: CallbackQuery):
    missing = await not_joined(client, cq.from_user.id)

    if missing is None:
        return await cq.answer(
            "Channel verify nahi ho raha. Admin ko bot permissions/ID check karni hogi.",
            show_alert=True,
        )

    if missing:
        await cq.answer(
            "Abhi bhi saare channels join nahi kiye!",
            show_alert=True,
        )

        try:
            await cq.message.edit_reply_markup(
                join_keyboard(get_force_channels())
            )
        except Exception:
            pass

        return

    await cq.answer("Shukriya! Ab kitab ka naam bhejo.")

    await cq.message.edit_text(
        welcome_text(cq.from_user),
        reply_markup=welcome_keyboard(),
    )


@app.on_callback_query(filters.regex(r"^pg\|"))
async def page_cb(client: Client, cq: CallbackQuery):
    _, page, token = cq.data.split("|", 2)
    query = _search_cache.get(token)

    if not query:
        return await cq.answer(
            "Ye search purani ho gayi, dobara naam bhejo.",
            show_alert=True,
        )

    text, kb = build_page(query, int(page), token)

    if text:
        await cq.message.edit_text(
            text,
            reply_markup=kb,
            parse_mode=enums.ParseMode.HTML,
        )

    await cq.answer()


@app.on_callback_query(filters.regex(r"^get\|"))
async def get_cb(client: Client, cq: CallbackQuery):
    missing = await not_joined(client, cq.from_user.id)

    if missing is None:
        return await cq.answer(
            "Channel verify nahi ho raha. Admin ko bot permissions/ID check karni hogi.",
            show_alert=True,
        )

    if missing:
        await cq.answer(
            "Pehle saare channels join karo!",
            show_alert=True,
        )

        return await client.send_message(
            cq.from_user.id,
            JOIN_TEXT,
            reply_markup=join_keyboard(get_force_channels()),
        )

    msg_id = int(cq.data.split("|")[1])

    try:
        sent = await client.copy_message(
            cq.from_user.id,
            DB_CHANNEL,
            msg_id,
        )

    except Exception as e:
        log.error("File bhejne me error: %s", e)

        return await cq.answer(
            "File nahi mil payi, baad me try karo.",
            show_alert=True,
        )

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


async def _startup_scan():
    try:
        found, last_id = await scan_db_channel(full=False)

        log.info(
            "Startup index: %s nayi files mili (last id %s)",
            found,
            last_id,
        )

    except Exception as e:
        log.error("Startup index fail: %s", e)


async def main():
    await app.start()

    log.info(
        "Bot start ho gaya. Force-join channels: %s",
        [c["ref"] for c in get_force_channels()],
    )
    log.info(
        "Auto-forward source groups: %s",
        SOURCE_GROUPS or "none",
    )

    if AUTO_INDEX_ON_START:
        asyncio.create_task(_startup_scan())

    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(main())
