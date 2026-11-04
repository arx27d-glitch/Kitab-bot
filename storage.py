"""Storage layer.

MongoStore  -> MongoDB (restart ke baad bhi data bacha rehta hai, RECOMMENDED)
SqliteStore -> local file (sirf test / VPS ke liye; Heroku/Railway/Render par restart me mit sakti hai)
"""
import re
import sqlite3
from typing import List, Optional, Tuple


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
            + " AND ".join(["search LIKE ?"] * len(words))
            + " ORDER BY title"
        )
        return [tuple(r) for r in self.db.execute(sql, [f"%{w}%" for w in words]).fetchall()]

    async def find_any(self, words: List[str], limit: int = 200) -> List[Tuple[int, str, int]]:
        """Kam se kam ek word match kare; jyada words match wale pehle."""
        if not words:
            return []
        like = [f"%{w}%" for w in words]
        score = " + ".join(["(search LIKE ?)"] * len(words))
        where = " OR ".join(["search LIKE ?"] * len(words))
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
