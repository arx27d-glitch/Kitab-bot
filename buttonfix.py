"""buttonfix.py - makes every inline button (Help / Home / About / Cancel / Close ...) reliable.

Use: put this file next to bot.py and add ONE line in bot.py, right after `load_dotenv()`:

    import buttonfix  # noqa: F401

What it fixes:
1. Colored buttons (ButtonStyle) are switched OFF. On some pyrogram forks / Telegram layers the
   styled keyboard makes the button tap do nothing. Set BUTTON_COLORS=true in env to turn them back on.
2. CallbackQuery.answer() no longer crashes the handler. If Telegram says "query too old / invalid"
   the old code stopped right there and never edited the message -> the button looked dead.
3. More handler workers, so one long job (/index, /broadcast) cannot block button taps.
4. Every button tap is written to the log ("CB click ...") so /logs shows if taps reach the bot.
"""
import logging
import os

from pyrogram import Client, enums
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import CallbackQuery

log = logging.getLogger("bookbot.buttonfix")

# 1) colored buttons off (unless asked for)
if os.environ.get("BUTTON_COLORS", "false").strip().lower() not in ("1", "true", "yes"):
    if hasattr(enums, "ButtonStyle"):
        try:
            delattr(enums, "ButtonStyle")
        except Exception:
            pass

# 2) safe answer + click log
_orig_answer = CallbackQuery.answer


async def _safe_answer(self, *args, **kwargs):
    try:
        log.info("CB click data=%r user=%s", self.data, getattr(self.from_user, "id", "?"))
    except Exception:
        pass
    try:
        return await _orig_answer(self, *args, **kwargs)
    except FloodWait:
        return None
    except RPCError as e:  # QUERY_ID_INVALID etc: ignore, the handler must go on and edit the message
        log.warning("callback answer failed (%s), continuing", e)
        return None
    except Exception as e:
        log.warning("callback answer error (%s), continuing", e)
        return None


CallbackQuery.answer = _safe_answer

# 3) more workers (default is small; long handlers block the button handlers)
_orig_init = Client.__init__


def _init(self, *args, **kwargs):
    kwargs.setdefault("workers", 32)
    _orig_init(self, *args, **kwargs)


Client.__init__ = _init

log.info("buttonfix loaded")
