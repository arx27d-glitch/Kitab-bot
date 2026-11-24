"""Launcher for the MOVIE HUB bot.  Run it with:  python start.py

bot.py is NOT changed. This file fixes the Railway login problem
("500 RPC_CALL_FAIL (caused by auth.ImportBotAuthorization)"):

1. LOGIN RETRY   - if Telegram answers with a temporary error (500, flood wait, network),
                   the bot waits and tries again (20s, 40s, 80s ... max 5 min) instead of crashing.
2. SAVED SESSION - the session file is kept in a folder that survives restarts (Railway Volume),
                   so after the first good login a restart does not log in with the token again.
3. SELF HEALING  - a broken saved session is deleted and the bot logs in fresh with BOT_TOKEN.
                   If BOT_TOKEN is changed, the old saved session is dropped automatically.

Session folder (first one that is set wins):
    SESSION_DIR env variable  ->  RAILWAY_VOLUME_MOUNT_PATH (Railway sets it by itself)  ->  none
With none, the session is lost on every restart, but the retry (1) still protects the bot.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pyrogram import Client  # noqa: E402
from pyrogram.errors import FloodWait, RPCError  # noqa: E402

SESSION_NAME = "bookbot"  # the name bot.py gives to its Client
MAX_TRIES = int(os.environ.get("LOGIN_MAX_TRIES", "12") or 12)

# errors that mean "the saved session is broken": delete it and log in again with the token
BAD_SESSION_IDS = {
    "AUTH_KEY_UNREGISTERED",
    "AUTH_KEY_INVALID",
    "AUTH_KEY_DUPLICATED",
    "SESSION_REVOKED",
    "SESSION_EXPIRED",
    "USER_DEACTIVATED",
}


def pick_session_dir():
    """Folder for the session file, or None (= Pyrogram's default folder, lost on restart)."""
    wanted = (os.environ.get("SESSION_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    if not wanted:
        return None
    path = Path(wanted)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return str(path)
    except Exception:
        return None


def delete_session_files(folder: Path):
    for f in folder.glob(f"{SESSION_NAME}.session*"):
        try:
            f.unlink()
        except Exception:
            pass


def drop_session_if_token_changed(folder: Path, token: str):
    """A saved session belongs to one bot. If BOT_TOKEN now belongs to another bot, forget the session."""
    bot_id = token.split(":", 1)[0].strip()
    if not bot_id:
        return
    marker = folder / f"{SESSION_NAME}.botid"
    try:
        old = marker.read_text().strip() if marker.exists() else ""
        if old and old != bot_id:
            delete_session_files(folder)
        marker.write_text(bot_id)
    except Exception:
        pass


SESSION_DIR = pick_session_dir()
if SESSION_DIR:
    drop_session_if_token_changed(Path(SESSION_DIR), os.environ.get("BOT_TOKEN", ""))

    # bot.py builds its Client without a workdir, so the session folder is added here
    _original_init = Client.__init__

    def _init_with_workdir(self, name, *args, **kwargs):
        kwargs.setdefault("workdir", SESSION_DIR)
        _original_init(self, name, *args, **kwargs)

    Client.__init__ = _init_with_workdir

import bot  # noqa: E402  (must come after the patch above, it creates the Client)

log = bot.log


def install_login_retry(app, max_tries: int = MAX_TRIES, first_delay: int = 20, sleep=asyncio.sleep):
    """Replaces app.start() with a version that retries temporary Telegram errors."""
    original_start = app.start

    async def start_with_retry(*args, **kwargs):
        delay = first_delay
        healed = False
        for attempt in range(1, max_tries + 1):
            try:
                return await original_start(*args, **kwargs)
            except FloodWait as e:
                wait = int(e.value) + 5
                log.warning("Telegram login: flood wait, waiting %ss (try %s/%s)", wait, attempt, max_tries)
                await sleep(wait)
            except Exception as e:
                if getattr(e, "ID", "") in BAD_SESSION_IDS and SESSION_DIR and not healed:
                    healed = True  # only once, so a different problem can't make an endless loop
                    log.warning("Saved session is not valid (%s). Deleting it and logging in with BOT_TOKEN.", e)
                    delete_session_files(Path(SESSION_DIR))
                    continue
                temporary = isinstance(e, (ConnectionError, TimeoutError, OSError)) or (
                    isinstance(e, RPCError) and getattr(e, "CODE", 0) >= 500
                )
                if not temporary or attempt == max_tries:
                    raise
                log.warning(
                    "Telegram login failed (%s: %s). Try %s/%s, next try in %ss",
                    type(e).__name__, e, attempt, max_tries, delay,
                )
                await sleep(delay)
                delay = min(delay * 2, 300)
        raise RuntimeError("Could not log in to Telegram after %s tries" % max_tries)

    app.start = start_with_retry


if __name__ == "__main__":
    if SESSION_DIR:
        saved = (Path(SESSION_DIR) / f"{SESSION_NAME}.session").exists()
        log.info(
            "Session folder: %s (%s)",
            SESSION_DIR,
            "saved session found, no token login needed" if saved else "no saved session yet, logging in with BOT_TOKEN",
        )
    else:
        log.warning(
            "No session folder (SESSION_DIR / Railway Volume not set). The session is lost on every restart, "
            "so the bot logs in with the token each time."
        )
    install_login_retry(bot.app)
    # PyroTGFork's app.run() no longer accepts a coroutine, so the loop is run directly
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot.main())
