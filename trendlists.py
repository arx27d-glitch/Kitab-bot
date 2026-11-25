"""trendlists.py - 3:4 posters + sectioned trending lists for the MOVIE HUB bot.

Free, NO API key needed (uses the same Cinemeta source as moviedb.py).

1) poster_34(url)   -> BytesIO of the poster cut to a 3:4 picture (600x800 JPEG), or None
2) get_category(key)-> list of titles for one trending section (see CATS / GENRES below)

How Bollywood / Hollywood / South / Other-wood is decided
  The "popular" catalog has no country field, so for every title of the popular list the bot reads
  the country + language from its Cinemeta meta page (cached for 3 days) and sorts it:
    India + Hindi              -> Bollywood
    English / USA, UK, ...     -> Hollywood
    India + Tamil/Telugu/...   -> South Indian
    everything else            -> Other-wood (Korean, Japanese, Turkish, Punjabi, Bengali ...)
  The first load takes ~10-20 seconds (it is started in the background when the bot starts),
  after that every list is instant (cache: TREND_CACHE_MIN minutes, default 360).

Env (all optional):  TREND_DEPTH_MOVIE=400  TREND_DEPTH_SERIES=200  TREND_CACHE_MIN=360
A bigger depth finds more Bollywood / other-wood titles but the first load is slower.
"""
import asyncio
import io
import logging
import os
import time
from collections import OrderedDict

from yarl import URL

import moviedb
from moviedb import CINEMETA, _cm_item, _get_json

log = logging.getLogger("bookbot.trend")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# ----------------------------------------------------------------------------
# 1) POSTER 3:4
# ----------------------------------------------------------------------------
_pcache: "OrderedDict[str, bytes]" = OrderedDict()


def _crop34(data: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    target = 3 / 4
    if w / h > target:  # too wide: cut the sides
        nw = int(h * target)
        x = (w - nw) // 2
        im = im.crop((x, 0, x + nw, h))
    else:  # too tall (normal 2:3 poster): cut a little from the bottom and top
        nh = int(w / target)
        y = int((h - nh) * 0.35)
        im = im.crop((0, y, w, y + nh))
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    im = im.resize((600, 800), resample)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


async def poster_34(url: str):
    """Poster as a 3:4 picture (BytesIO) or None if it could not be made (the caller then sends the plain url)."""
    if not url:
        return None
    data = _pcache.get(url)
    if data is None:
        raw = await moviedb.fetch_image(url)
        if not raw:
            return None
        try:
            data = await asyncio.to_thread(_crop34, raw.getvalue())
        except Exception as e:  # Pillow missing / broken image
            log.warning("Could not make the 3:4 poster (%s: %s)", type(e).__name__, e)
            return None
        _pcache[url] = data
        while len(_pcache) > 150:
            _pcache.popitem(last=False)
    buf = io.BytesIO(data)
    buf.name = "poster.jpg"
    return buf


# ----------------------------------------------------------------------------
# 2) SECTIONS
# ----------------------------------------------------------------------------
# key -> (kind, pool, wanted groups or "new" or None = all, how many titles)
CATS = OrderedDict(
    [
        ("bm", ("movie", "mt", {"bolly"}, 10)),                                  # Bollywood Top 10
        ("hm", ("movie", "mt", {"holly"}, 10)),                                  # Hollywood Top 10
        ("sm", ("movie", "mt", {"south"}, 10)),                                  # Tollywood / Kollywood ...
        ("om", ("movie", "mt", {"other", "indian_other"}, 10)),                  # Korean, Japanese, Punjabi ...
        ("bs", ("series", "st", {"bolly"}, 10)),                                 # Hindi / Indian series
        ("hs", ("series", "st", {"holly"}, 10)),                                 # English series
        ("os", ("series", "st", {"other", "south", "indian_other"}, 10)),        # K-drama, anime ...
        ("nw", ("movie", "mt", "new", 30)),                                      # new releases
        ("pm", ("movie", "mt", None, 50)),                                       # popular movies
        ("ps", ("series", "st", None, 50)),                                      # popular series
        ("tm", ("movie", "mr", None, 50)),                                       # top rated movies
        ("ts", ("series", "sr", None, 50)),                                      # top rated series
    ]
)
ICONS = {
    "bm": "🇮🇳", "hm": "🇺🇸", "sm": "🌴", "om": "🌏", "bs": "📺", "hs": "📺", "os": "🌏",
    "nw": "🆕", "pm": "🔥", "ps": "🔥", "tm": "⭐", "ts": "⭐",
}
SHOW_LANG = {"sm", "om", "os"}  # these sections show the language of each title

GENRES = ["Action", "Comedy", "Horror", "Thriller", "Romance", "Sci-Fi", "Animation", "Crime",
          "Drama", "Adventure", "Fantasy", "Mystery", "Family", "War", "Biography", "Documentary"]

# pool -> (kind, cinemeta catalog, depth, read country/language?)
POOLS = {
    "mt": ("movie", "top", lambda: _env_int("TREND_DEPTH_MOVIE", 400), True),
    "st": ("series", "top", lambda: _env_int("TREND_DEPTH_SERIES", 200), True),
    "mr": ("movie", "imdbRating", lambda: 100, False),
    "sr": ("series", "imdbRating", lambda: 100, False),
}


def valid(key: str) -> bool:
    return key in CATS or (key.startswith("g_") and key[2:] in GENRES)


def _ttl() -> int:
    return max(_env_int("TREND_CACHE_MIN", 360), 5) * 60


# ---- country / language -> group
SOUTH = {"tamil", "telugu", "malayalam", "kannada", "tulu"}
WEST = ("usa", "united states", "uk", "united kingdom", "canada", "australia", "ireland", "new zealand")


def classify(meta: dict):
    """(group, language): bolly | holly | south | indian_other | other | unknown"""
    country = (meta.get("country") or "").lower()
    langs = [x.strip() for x in (meta.get("language") or "").lower().split(",") if x.strip()]
    primary = langs[0] if langs else ""
    western = any(w in country for w in WEST)
    if "india" in country:
        if primary == "english" and western:  # an English film that India co-produced
            return "holly", "english"
        if primary in SOUTH:
            return "south", primary
        if primary == "hindi" or "hindi" in langs:
            return "bolly", "hindi"
        return "indian_other", primary
    if not country and not langs:
        return "unknown", ""
    if primary == "english" or (not primary and western) or (western and "english" in langs):
        return "holly", "english"
    return "other", primary


# ---- loading
_pools: dict = {}      # pool -> (valid until, items)
_locks: dict = {}      # pool -> lock (one load at a time)
_genres: dict = {}     # genre -> (valid until, items)
_meta: dict = {}       # imdb id -> (valid until, {"country", "language"})
_index: dict = {}      # imdb id -> item (for the buttons, which only carry the id)


def _fresh(entry) -> bool:
    return bool(entry) and entry[0] > time.time()


async def _page(kind: str, catalog: str, skip: int, genre: str = ""):
    parts = []
    if genre:
        parts.append(f"genre={genre}")
    if skip:
        parts.append(f"skip={skip}")
    path = f"{CINEMETA}/catalog/{kind}/{catalog}" + ("/" + "&".join(parts) if parts else "") + ".json"
    data = await _get_json(URL(path, encoded=True), timeout=10)
    return [m for m in ((data or {}).get("metas") or []) if isinstance(m, dict)]


async def _load_items(kind: str, catalog: str, depth: int, genre: str = "") -> list:
    first = await _page(kind, catalog, 0, genre)
    if not first:
        return []
    size = len(first)
    skips = [s for s in range(size, depth, size)] if size > 0 else []
    rest = await asyncio.gather(*(_page(kind, catalog, s, genre) for s in skips), return_exceptions=True)
    metas = list(first)
    for r in rest:
        if not isinstance(r, Exception):
            metas.extend(r)
    items, seen = [], set()
    for m in metas:
        item = _cm_item(m, kind)
        if item["title"] and item["id"] and len(item["id"]) <= 40 and item["id"] not in seen:
            seen.add(item["id"])
            item["group"], item["lang"] = "unknown", ""
            items.append(item)
    return items[:depth] if depth else items


async def _meta_of(kind: str, imdb_id: str) -> dict:
    hit = _meta.get(imdb_id)
    if _fresh(hit):
        return hit[1]
    data = await _get_json(URL(f"{CINEMETA}/meta/{kind}/{imdb_id}.json", encoded=True), timeout=8)
    m = (data or {}).get("meta") or {}
    info = {"country": str(m.get("country") or ""), "language": str(m.get("language") or "")}
    if len(_meta) > 6000:
        _meta.clear()
    _meta[imdb_id] = (time.time() + 3 * 86400, info)
    return info


async def _enrich(items: list, kind: str):
    gate = asyncio.Semaphore(12)

    async def one(item):
        if not item["id"].startswith("tt"):
            return
        async with gate:
            try:
                info = await _meta_of(kind, item["id"])
            except Exception:
                return  # this title stays "unknown" (it is still in the popular lists)
        item["group"], item["lang"] = classify(info)

    await asyncio.gather(*(one(i) for i in items))


async def _pool(name: str) -> list:
    hit = _pools.get(name)
    if _fresh(hit):
        return hit[1]
    lock = _locks.setdefault(name, asyncio.Lock())
    async with lock:
        hit = _pools.get(name)
        if _fresh(hit):
            return hit[1]
        kind, catalog, depth, enrich = POOLS[name]
        try:
            items = await _load_items(kind, catalog, depth())
            if enrich and items:
                await _enrich(items, kind)
        except Exception as e:
            log.warning("Trending pool %s failed: %s: %s", name, type(e).__name__, e)
            return hit[1] if hit else []  # an old list is better than nothing
        if items:
            _pools[name] = (time.time() + _ttl(), items)
            for it in items:
                _index[it["id"]] = it
            if len(_index) > 5000:
                _index.clear()
                _index.update((it["id"], it) for it in items)
        return items


async def get_category(key: str) -> list:
    """Titles of one section ([] = not available right now)."""
    if key.startswith("g_"):
        genre = key[2:]
        if genre not in GENRES:
            return []
        hit = _genres.get(genre)
        if _fresh(hit):
            return hit[1]
        try:
            items = await _load_items("movie", "top", 50, genre)
        except Exception as e:
            log.warning("Genre %s failed: %s", genre, e)
            return hit[1] if hit else []
        if items:
            _genres[genre] = (time.time() + 3600, items)
            for it in items:
                _index.setdefault(it["id"], it)
        return items

    spec = CATS.get(key)
    if not spec:
        return []
    kind, pool, want, limit = spec
    items = await _pool(pool)
    if want is None:
        out = items
    elif want == "new":
        year = time.gmtime().tm_year
        out = [i for i in items if i.get("year", "").isdigit() and int(i["year"]) >= year - 1]
    else:
        out = [i for i in items if i.get("group") in want]
    return out[:limit]


def is_cached(key: str) -> bool:
    if key.startswith("g_"):
        return _fresh(_genres.get(key[2:]))
    spec = CATS.get(key)
    return bool(spec) and _fresh(_pools.get(spec[1]))


def find_item(item_id: str):
    return _index.get(item_id)


async def warm():
    """Loads the big lists in the background (called when the bot starts)."""
    for name in ("mt", "st", "mr", "sr"):
        try:
            await _pool(name)
        except Exception as e:
            log.warning("Trending warm-up of %s failed: %s", name, e)
    counts = {k: len(_pools[name][1]) for k, name in (("movies", "mt"), ("series", "st")) if name in _pools}
    log.info("Trending lists ready: %s", counts)
