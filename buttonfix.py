"""buttonfix.py - makes every inline button (Help / Home / About / Language / Close ...) reliable.

bot.py already has `import buttonfix` right after load_dotenv(). Nothing else has to change in bot.py.

What this file does:
1. PRIVATE CHAT FIX. In a private chat, Telegram does not hand the message of a button press to the
   library any more, so `callback_query.message` was None. bot.py then showed the "expired" alert or did
   nothing, so Help / About / Home / Trending / Language looked dead (in groups the library builds a
   fallback message, so groups worked). Now the message is fetched with the special "message of this
   callback query" call, and if even that fails a small message object (chat id + message id) is built,
   so editing and deleting the message always work.
2. Colored buttons are NOT switched off any more. The old version deleted enums.ButtonStyle: that removed
   the colors and also breaks PyroTGFork itself, because it reads enums.ButtonStyle every time a keyboard
   is sent or received.
3. CallbackQuery.answer() no longer crashes the handler when Telegram says "query too old / invalid".
4. More handler workers, so one long job (/index, /broadcast) cannot block button taps.
5. Every button tap is written to the log ("CB click ...") so /logs shows that taps reach the bot.
"""
import logging

from pyrogram import Client, raw, types, utils
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import CallbackQuery

log = logging.getLogger("bookbot.buttonfix")

# ---------------------------------------------------------------------------------------------
# 1) a button press always gets a usable message
# ---------------------------------------------------------------------------------------------
_orig_parse = CallbackQuery._parse


def _usable(msg) -> bool:
    """A message we can edit / delete / reply to: it exists, is not 'empty' and knows its chat."""
    return msg is not None and not getattr(msg, "empty", False) and getattr(msg, "chat", None) is not None


def _minimal_message(client, cb, users, chats):
    """Message object with only the chat and the message id (enough to edit, delete and reply)."""
    peer = cb.peer
    try:
        if isinstance(peer, raw.types.PeerUser):
            chat = types.Chat._parse_user_chat(client, users[peer.user_id])
        elif isinstance(peer, raw.types.PeerChat):
            chat = types.Chat._parse_chat_chat(client, chats[peer.chat_id])
        else:
            chat = types.Chat._parse_channel_chat(client, chats[peer.channel_id])
        return types.Message(client=client, id=cb.msg_id, date=utils.timestamp_to_datetime(0), chat=chat)
    except Exception as e:
        log.warning("Could not build a fallback message for a button press (%s)", e)
        return None


def _bare_query(client, cb, users):
    """CallbackQuery built by hand, used only when the library itself failed to parse the update."""
    data = getattr(cb, "data", None)
    if data:
        try:
            data = data.decode()
        except (UnicodeDecodeError, AttributeError):
            pass
    return CallbackQuery(
        client=client,
        id=str(cb.query_id),
        from_user=types.User._parse(client, users[cb.user_id]),
        chat_instance=str(cb.chat_instance),
        message=None,
        data=data,
        game_short_name=getattr(cb, "game_short_name", None),
    )


async def _parse_with_message(client, callback_query, users, chats):
    try:
        cq = await _orig_parse(client, callback_query, users, chats)
    except Exception as e:  # e.g. the library could not load the message: do not lose the tap
        log.warning("CallbackQuery parse failed (%s: %s), using a fallback", type(e).__name__, e)
        cq = _bare_query(client, callback_query, users)

    if not isinstance(callback_query, raw.types.UpdateBotCallbackQuery) or _usable(cq.message):
        return cq

    msg = None
    try:  # the call made for exactly this: "the message that carried the pressed button"
        msg = await client.get_callback_query_message(
            chat_id=utils.get_peer_id(callback_query.peer),
            message_id=callback_query.msg_id,
            callback_query_id=callback_query.query_id,
        )
    except Exception as e:
        log.info("get_callback_query_message failed (%s: %s)", type(e).__name__, e)
    if not _usable(msg):
        msg = _minimal_message(client, callback_query, users, chats)
    if msg is not None:
        cq.message = msg
    return cq


CallbackQuery._parse = staticmethod(_parse_with_message)

# ---------------------------------------------------------------------------------------------
# 3) safe answer + 5) click log
# ---------------------------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------------------------
# 4) more workers (long handlers must not block the button handlers)
# ---------------------------------------------------------------------------------------------
_orig_init = Client.__init__


def _init(self, *args, **kwargs):
    kwargs.setdefault("workers", 32)
    _orig_init(self, *args, **kwargs)


Client.__init__ = _init

log.info("buttonfix loaded")
