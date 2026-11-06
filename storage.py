"""Storage layer.

MongoStore  -> MongoDB (restart ke baad bhi data bacha rehta hai, RECOMMENDED)
SqliteStore -> local file (sirf test / VPS ke liye; Heroku/Railway/Render par restart me mit sakti hai)
"""
import asyncio
import logging
import re
import sqlite3
from typing import List, Optional, Tuple

log = logging.getLogger("bookbot.storage")


def _like(word: str) -> str:
    """LIKE pattern for a word; % and _ typed by a user are NOT wildcards."""
    return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class SqliteStore:
    persistent = False

    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS files(
                msg_id INTEGER PRIMARY KEY, title TEXT, search TEXT, size INTEGER,
                file_id TEXT, caption TEXT);
            CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS forwarded(uid TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS channels(slot INTEGER PRIMARY KEY, ref TEXT, link TEXT);
            """
        )
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(files)")}
        for col in ("file_id", "caption"):
            if col not in cols:
                self.db.execute(f"ALTER TABLE files ADD COLUMN {col} TEXT")
        self.db.commit()

    async def init(self):
        return None

    # files
    async def upsert_file(self, msg_id, title, search, size, file_id, caption):
        self.db.execute(
            "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
            (msg_id, title, search, size, file_id, caption),
        )
        self.db.commit()

    async def delete_file(self, msg_id: int) -> bool:
        """Removes one file from the database. True if it existed."""
        cur = self.db.execute("DELETE FROM files WHERE msg_id=?", (msg_id,))
        self.db.commit()
        return cur.rowcount > 0

    async def clear_files(self) -> int:
        """Removes ALL files from the database. Returns how many were removed."""
        cur = self.db.execute("DELETE FROM files")
        self.db.commit()
        return cur.rowcount

    async def find(self, words: List[str]) -> List[Tuple[int, str, int]]:
        if not words:
            return []
        sql = (
            "SELECT msg_id, title, size FROM files WHERE "
            + " AND ".join(["search LIKE ? ESCAPE '\\'"] * len(words))
            + " ORDER BY title LIMIT 2000"
        )
        return [tuple(r) for r in self.db.execute(sql, [_like(w) for w in words]).fetchall()]

    async def find_any(self, words: List[str], limit: int = 200) -> List[Tuple[int, str, int]]:
        """Kam se kam ek word match kare; jyada words match wale pehle."""
        if not words:
            return []
        like = [_like(w) for w in words]
        score = " + ".join(["(search LIKE ? ESCAPE '\\')"] * len(words))
        where = " OR ".join(["search LIKE ? ESCAPE '\\'"] * len(words))
        sql = (
            f"SELECT msg_id, title, size FROM files WHERE {where} "
            f"ORDER BY ({score}) DESC, title LIMIT {int(limit)}"
        )
        return [tuple(r) for r in self.db.execute(sql, like + like).fetchall()]

    async def get_file(self, msg_id: int) -> Optional[dict]:
        r = self.db.execute(
            "SELECT msg_id, title, file_id, caption, size FROM files WHERE msg_id=?", (msg_id,)
        ).fetchone()
        return (
            {"msg_id": r[0], "title": r[1], "file_id": r[2], "caption": r[3], "size": r[4] or 0}
            if r
            else None
        )

    async def count_files(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    # users
    async def add_user(self, user_id: int):
        self.db.execute("INSERT OR IGNORE INTO users VALUES(?)", (user_id,))
        self.db.commit()

    async def all_user_ids(self) -> List[int]:
        return [r[0] for r in self.db.execute("SELECT user_id FROM users").fetchall()]

    async def delete_user(self, user_id: int):
        self.db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        self.db.commit()

    async def count_users(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # forwarded (duplicate rokne ke liye)
    async def is_forwarded(self, uid: str) -> bool:
        return self.db.execute("SELECT 1 FROM forwarded WHERE uid=?", (uid,)).fetchone() is not None

    async def mark_forwarded(self, uid: str):
        self.db.execute("INSERT OR IGNORE INTO forwarded VALUES(?)", (uid,))
        self.db.commit()

    # meta
    async def get_meta(self, key: str, default: str = "") -> str:
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    async def set_meta(self, key: str, value: str):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))
        self.db.commit()

    # force-join channels
    async def get_channels(self) -> List[Tuple[int, str, str]]:
        return [tuple(r) for r in self.db.execute("SELECT slot, ref, link FROM channels").fetchall()]

    async def set_channel(self, slot: int, ref: str, link: str):
        self.db.execute("INSERT OR REPLACE INTO channels VALUES(?,?,?)", (slot, ref, link))
        self.db.commit()

    async def del_channel(self, slot: int):
        self.db.execute("DELETE FROM channels WHERE slot=?", (slot,))
        self.db.commit()


class MongoStore:
    persistent = True

    def __init__(self, uri: str, name: str = "bookbot"):
        from motor.motor_asyncio import AsyncIOMotorClient

        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[name]

    async def init(self):
        await self.db.command("ping")  # connection galat ho to start par hi error aa jaye

    # files
    async def upsert_file(self, msg_id, title, search, size, file_id, caption):
        await self.db.files.replace_one(
            {"_id": msg_id},
            {
                "_id": msg_id,
                "title": title,
                "search": search,
                "size": size,
                "file_id": file_id,
                "caption": caption,
            },
            upsert=True,
        )

    async def delete_file(self, msg_id: int) -> bool:
        """Removes one file from the database. True if it existed."""
        res = await self.db.files.delete_one({"_id": msg_id})
        return res.deleted_count > 0

    async def clear_files(self) -> int:
        """Removes ALL files from the database. Returns how many were removed."""
        res = await self.db.files.delete_many({})
        return res.deleted_count

    async def find(self, words: List[str]) -> List[Tuple[int, str, int]]:
        if not words:
            return []
        conds = [{"search": {"$regex": re.escape(w)}} for w in words]
        cur = self.db.files.find({"$and": conds}, {"title": 1, "size": 1}).sort("title", 1)
        docs = await cur.to_list(length=2000)
        return [(d["_id"], d.get("title", ""), d.get("size", 0)) for d in docs]

    async def find_any(self, words: List[str], limit: int = 200) -> List[Tuple[int, str, int]]:
        """Kam se kam ek word match kare; jyada words match wale pehle."""
        if not words:
            return []
        conds = [{"search": {"$regex": re.escape(w)}} for w in words]
        cur = self.db.files.find({"$or": conds}, {"title": 1, "size": 1, "search": 1}).limit(1000)
        docs = await cur.to_list(length=1000)

        def score(d):
            text = d.get("search", "")
            return sum(1 for w in words if w in text)

        docs.sort(key=lambda d: (-score(d), d.get("title", "")))
        return [(d["_id"], d.get("title", ""), d.get("size", 0)) for d in docs[:limit]]

    async def get_file(self, msg_id: int) -> Optional[dict]:
        d = await self.db.files.find_one({"_id": msg_id})
        if not d:
            return None
        return {
            "msg_id": d["_id"],
            "title": d.get("title", ""),
            "file_id": d.get("file_id"),
            "caption": d.get("caption", ""),
            "size": d.get("size", 0),
        }

    async def count_files(self) -> int:
        return await self.db.files.count_documents({})

    # users
    async def add_user(self, user_id: int):
        await self.db.users.replace_one({"_id": user_id}, {"_id": user_id}, upsert=True)

    async def all_user_ids(self) -> List[int]:
        return [d["_id"] async for d in self.db.users.find({}, {"_id": 1})]

    async def delete_user(self, user_id: int):
        await self.db.users.delete_one({"_id": user_id})

    async def count_users(self) -> int:
        return await self.db.users.count_documents({})

    # forwarded
    async def is_forwarded(self, uid: str) -> bool:
        return await self.db.forwarded.find_one({"_id": uid}) is not None

    async def mark_forwarded(self, uid: str):
        await self.db.forwarded.replace_one({"_id": uid}, {"_id": uid}, upsert=True)

    # meta
    async def get_meta(self, key: str, default: str = "") -> str:
        d = await self.db.meta.find_one({"_id": key})
        return d["value"] if d else default

    async def set_meta(self, key: str, value: str):
        await self.db.meta.replace_one({"_id": key}, {"_id": key, "value": value}, upsert=True)

    # force-join channels
    async def get_channels(self) -> List[Tuple[int, str, str]]:
        return [(d["_id"], d.get("ref", ""), d.get("link", "")) async for d in self.db.channels.find({})]

    async def set_channel(self, slot: int, ref: str, link: str):
        await self.db.channels.replace_one(
            {"_id": slot}, {"_id": slot, "ref": ref, "link": link}, upsert=True
        )

    async def del_channel(self, slot: int):
        await self.db.channels.delete_one({"_id": slot})


# ----------------------------------------------------------------------------
# MULTI MONGODB: 1 se 10 tak MongoDB. Jo bhar jaye uske baad files agle DB me jati hain.
# ----------------------------------------------------------------------------
def _is_quota_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        "quota" in msg
        or getattr(e, "code", None) == 8000
        or "no space left" in msg
        or ("disk" in msg and "full" in msg)
    )


class MultiMongoStore:
    """Files are spread over several MongoDB databases.

    - New files go to the first database that still has space (DB 1, then DB 2, ...).
    - When a database reaches the size limit (or Mongo says "over quota"), it is marked full and
      the next one is used. Admins get a message about it.
    - Search / count / delete look in ALL databases, so the user never notices the split.
    - Users, channels, admins, settings (small data) live in DB 1 only.
    """

    persistent = True

    def __init__(self, uris: List[str], name: str = "bookbot", limit_mb: int = 450):
        self.stores = [MongoStore(u, name) for u in uris]
        self.limit = int(limit_mb) * 1024 * 1024
        self.sizes = [0] * len(self.stores)
        self.full = set()
        self.active = 0
        self._loc = {}  # msg_id -> index of the database that holds the file
        self._writes = 0
        self._alerted_all_full = False
        self.notify = None  # optional: async function(text) set by the bot to message admins

    def __getattr__(self, name):
        # users / meta / channels / forwarded etc. are handled by the first database
        if name == "stores":
            raise AttributeError(name)
        return getattr(self.stores[0], name)

    async def init(self):
        for i, st in enumerate(self.stores):
            try:
                await st.init()
            except Exception as e:
                raise RuntimeError(f"MongoDB #{i + 1} se connect nahi ho paya: {e}")
        for i, st in enumerate(self.stores):
            async for d in st.db.files.find({}, {"_id": 1}):
                self._loc.setdefault(d["_id"], i)
        await self._refresh_sizes()
        first = self._first_free()
        self.active = first if first is not None else len(self.stores) - 1
        log.info(
            "MongoDB: %s database(s), %s files, active = DB %s",
            len(self.stores), len(self._loc), self.active + 1,
        )

    # ---- size handling
    async def _refresh_sizes(self):
        for i, st in enumerate(self.stores):
            try:
                stats = await st.db.command("dbStats")
                self.sizes[i] = int(stats.get("storageSize", 0)) + int(stats.get("indexSize", 0))
                if self.sizes[i] >= self.limit:
                    self.full.add(i)
                else:
                    self.full.discard(i)
            except Exception as e:
                log.warning("Could not read size of MongoDB #%s: %s", i + 1, e)

    def _first_free(self) -> Optional[int]:
        for i in range(len(self.stores)):
            if i not in self.full:
                return i
        return None

    async def _alert(self, text: str):
        log.warning(text.replace("\n", " "))
        if self.notify:
            try:
                await self.notify(text)
            except Exception:
                pass

    # ---- files
    async def upsert_file(self, msg_id, title, search, size, file_id, caption):
        self._writes += 1
        if self._writes % 100 == 0:
            await self._refresh_sizes()

        # already stored somewhere -> update it there
        idx = self._loc.get(msg_id)
        if idx is not None:
            try:
                await self.stores[idx].upsert_file(msg_id, title, search, size, file_id, caption)
                return
            except Exception as e:
                if not _is_quota_error(e):
                    raise
                self.full.add(idx)
                try:
                    await self.stores[idx].delete_file(msg_id)
                except Exception:
                    pass
                self._loc.pop(msg_id, None)

        while True:
            i = self._first_free()
            if i is None:
                if not self._alerted_all_full:
                    self._alerted_all_full = True
                    await self._alert(
                        "▲ <b>All MongoDB databases are full!</b>\nNew files can't be saved. "
                        "Add another <code>MONGO_URI_n</code> (up to 10) or free some space."
                    )
                raise RuntimeError("Saare MongoDB databases full hain")
            try:
                await self.stores[i].upsert_file(msg_id, title, search, size, file_id, caption)
            except Exception as e:
                if not _is_quota_error(e):
                    raise
                self.full.add(i)
                continue
            self._loc[msg_id] = i
            if i != self.active:
                old, self.active = self.active, i
                await self._alert(
                    f"◇ <b>MongoDB #{old + 1} is full</b>\nNew files now go to <b>MongoDB #{i + 1}</b>."
                )
            return

    async def delete_file(self, msg_id: int) -> bool:
        idx = self._loc.pop(msg_id, None)
        if idx is None:
            return False
        return await self.stores[idx].delete_file(msg_id)

    async def clear_files(self) -> int:
        total = 0
        for st in self.stores:
            total += await st.clear_files()
        self._loc.clear()
        self.full.clear()
        self.active = 0
        self._alerted_all_full = False
        return total

    async def get_file(self, msg_id: int) -> Optional[dict]:
        idx = self._loc.get(msg_id)
        if idx is None:
            return None
        return await self.stores[idx].get_file(msg_id)

    async def _all(self, make):
        """Runs the same query on every database; a database that fails is skipped."""
        results = await asyncio.gather(*(make(st) for st in self.stores), return_exceptions=True)
        merged = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.warning("MongoDB #%s query failed: %s", i + 1, r)
            else:
                merged.extend(r)
        return merged

    async def find(self, words: List[str]) -> List[Tuple[int, str, int]]:
        merged = await self._all(lambda st: st.find(words))
        merged.sort(key=lambda r: r[1])
        return merged

    async def find_any(self, words: List[str], limit: int = 200) -> List[Tuple[int, str, int]]:
        merged = await self._all(lambda st: st.find_any(words, limit))

        def score(r):
            t = (r[1] or "").lower()
            return sum(1 for w in words if w in t)

        merged.sort(key=lambda r: (-score(r), r[1]))
        return merged[:limit]

    async def count_files(self) -> int:
        counts = await self._all(lambda st: _as_list(st.count_files()))
        return sum(counts)

    # ---- info for /stats
    async def status(self) -> List[dict]:
        await self._refresh_sizes()
        counts = await asyncio.gather(*(st.count_files() for st in self.stores), return_exceptions=True)
        first_free = self._first_free()
        out = []
        for i in range(len(self.stores)):
            if i in self.full:
                state = "full"
            elif i == first_free:
                state = "active"
            else:
                state = "standby"
            out.append(
                {
                    "n": i + 1,
                    "used_mb": self.sizes[i] / (1024 * 1024),
                    "files": counts[i] if isinstance(counts[i], int) else 0,
                    "state": state,
                }
            )
        return out


async def _as_list(coro):
    return [await coro]
