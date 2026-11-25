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

Why the Indian sections used to be empty
  The popular catalog is almost all Hollywood: very few Indian titles are inside its top 400, so
  Bollywood / South / Indian series / Other-wood / Other series had (almost) nothing to show.
  Now these five sections show the titles that are popular right now (if any) and are then filled up
  to 10 from the curated lists in SEEDS below. Each curated title is looked up in Cinemeta, so the
  rating, year and poster are still real. Add or remove titles in SEEDS whenever you like.

Env (all optional):  TREND_DEPTH_MOVIE=400  TREND_DEPTH_SERIES=200  TREND_CACHE_MIN=360
A bigger depth finds more Bollywood / other-wood titles but the first load is slower.
"""
import asyncio
import io
import logging
import os
import re
import time
from collections import Counter, OrderedDict
from urllib.parse import quote

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

# ----------------------------------------------------------------------------
# CURATED TITLES for the sections the popular catalog can not fill (see the top of this file).
#   section -> [(name, year, language), ...]   Best / most popular first.
# The name is also what the user's search uses when he taps the button, so write it the way a file
# would be named (no ":" needed). A title that Cinemeta can't find is simply skipped, so a long list is safe.
# ----------------------------------------------------------------------------
SEEDS = {
    # Bollywood movies
    "bm": [
        ("Dhurandhar", 2025, "hindi"), ("Saiyaara", 2025, "hindi"), ("Chhaava", 2025, "hindi"),
        ("Jawan", 2023, "hindi"), ("Pathaan", 2023, "hindi"), ("Animal", 2023, "hindi"),
        ("Stree 2", 2024, "hindi"), ("12th Fail", 2023, "hindi"), ("Laapataa Ladies", 2023, "hindi"),
        ("Dangal", 2016, "hindi"), ("3 Idiots", 2009, "hindi"), ("PK", 2014, "hindi"),
        ("Gadar 2", 2023, "hindi"), ("Dunki", 2023, "hindi"), ("Kabir Singh", 2019, "hindi"),
        ("Uri The Surgical Strike", 2019, "hindi"), ("Bajrangi Bhaijaan", 2015, "hindi"),
        ("Sultan", 2016, "hindi"), ("Drishyam 2", 2022, "hindi"),
        ("Brahmastra Part One Shiva", 2022, "hindi"), ("Gangubai Kathiawadi", 2022, "hindi"),
        ("The Kashmir Files", 2022, "hindi"), ("Tiger 3", 2023, "hindi"), ("Fighter", 2024, "hindi"),
        ("Bhool Bhulaiyaa 3", 2024, "hindi"), ("Singham Again", 2024, "hindi"),
        ("Sitaare Zameen Par", 2025, "hindi"), ("Housefull 5", 2025, "hindi"), ("War 2", 2025, "hindi"),
        ("Sikandar", 2025, "hindi"), ("Kesari Chapter 2", 2025, "hindi"), ("Raid 2", 2025, "hindi"),
        ("Andhadhun", 2018, "hindi"), ("Tumbbad", 2018, "hindi"), ("Munjya", 2024, "hindi"),
    ],
    # South Indian movies (Telugu, Tamil, Kannada, Malayalam)
    "sm": [
        ("RRR", 2022, "telugu"), ("Pushpa 2 The Rule", 2024, "telugu"), ("KGF Chapter 2", 2022, "kannada"),
        ("Baahubali 2 The Conclusion", 2017, "telugu"), ("Kantara", 2022, "kannada"),
        ("Kantara Chapter 1", 2025, "kannada"), ("Salaar Part 1 Ceasefire", 2023, "telugu"),
        ("Kalki 2898 AD", 2024, "telugu"), ("Leo", 2023, "tamil"), ("Jailer", 2023, "tamil"),
        ("Vikram", 2022, "tamil"), ("Pushpa The Rise", 2021, "telugu"), ("KGF Chapter 1", 2018, "kannada"),
        ("Baahubali The Beginning", 2015, "telugu"), ("Ponniyin Selvan I", 2022, "tamil"),
        ("Master", 2021, "tamil"), ("Lucifer", 2019, "malayalam"), ("L2 Empuraan", 2025, "malayalam"),
        ("Manjummel Boys", 2024, "malayalam"), ("Premalu", 2024, "malayalam"),
        ("Aavesham", 2024, "malayalam"), ("Devara Part 1", 2024, "telugu"),
        ("Lucky Baskhar", 2024, "telugu"), ("Amaran", 2024, "tamil"), ("Maharaja", 2024, "tamil"),
        ("Coolie", 2025, "tamil"), ("HanuMan", 2024, "telugu"), ("Sita Ramam", 2022, "telugu"),
        ("Jai Bhim", 2021, "tamil"), ("Asuran", 2019, "tamil"), ("Kaithi", 2019, "tamil"),
        ("Soorarai Pottru", 2020, "tamil"), ("Drishyam", 2013, "malayalam"),
        ("Lokah Chapter 1 Chandra", 2025, "malayalam"), ("Thudarum", 2025, "malayalam"),
        ("Kumbalangi Nights", 2019, "malayalam"), ("Premam", 2015, "malayalam"), ("Eega", 2012, "telugu"),
        ("Ala Vaikunthapurramuloo", 2020, "telugu"), ("Thug Life", 2025, "tamil"),
        ("They Call Him OG", 2025, "telugu"), ("Game Changer", 2025, "telugu"), ("Kanguva", 2024, "tamil"),
    ],
    # Hindi / Indian web series
    "bs": [
        ("Panchayat", 2020, "hindi"), ("Mirzapur", 2018, "hindi"), ("The Family Man", 2019, "hindi"),
        ("Sacred Games", 2018, "hindi"), ("Scam 1992", 2020, "hindi"), ("Delhi Crime", 2019, "hindi"),
        ("Kota Factory", 2019, "hindi"), ("Asur", 2020, "hindi"), ("Paatal Lok", 2020, "hindi"),
        ("Made in Heaven", 2019, "hindi"), ("Special Ops", 2020, "hindi"), ("Farzi", 2023, "hindi"),
        ("Rocket Boys", 2022, "hindi"), ("Gullak", 2019, "hindi"), ("Aspirants", 2021, "hindi"),
        ("Criminal Justice", 2019, "hindi"), ("Heeramandi The Diamond Bazaar", 2024, "hindi"),
        ("Kohrra", 2023, "hindi"), ("Jamtara", 2020, "hindi"), ("IC 814 The Kandahar Hijack", 2024, "hindi"),
        ("The Railway Men", 2023, "hindi"), ("Poacher", 2024, "hindi"), ("Black Warrant", 2025, "hindi"),
        ("Aarya", 2020, "hindi"), ("Breathe", 2018, "hindi"), ("Inside Edge", 2017, "hindi"),
        ("Bandish Bandits", 2020, "hindi"), ("Dahaad", 2023, "hindi"), ("Class", 2023, "hindi"),
        ("Gyaarah Gyaarah", 2024, "hindi"), ("Mumbai Diaries 26 11", 2021, "hindi"),
    ],
    # other-wood movies (Korean, Japanese, Chinese, European ...)
    "om": [
        ("Parasite", 2019, "korean"), ("Train to Busan", 2016, "korean"), ("Oldboy", 2003, "korean"),
        ("Spirited Away", 2001, "japanese"), ("Your Name", 2016, "japanese"),
        ("Demon Slayer Mugen Train", 2020, "japanese"), ("Godzilla Minus One", 2023, "japanese"),
        ("Weathering with You", 2019, "japanese"), ("Shoplifters", 2018, "japanese"),
        ("The Handmaiden", 2016, "korean"), ("Burning", 2018, "korean"),
        ("Decision to Leave", 2022, "korean"), ("Memories of Murder", 2003, "korean"),
        ("The Wailing", 2016, "korean"), ("Miracle in Cell No 7", 2013, "korean"),
        ("The Roundup", 2022, "korean"), ("Princess Mononoke", 1997, "japanese"),
        ("A Silent Voice", 2016, "japanese"), ("Grave of the Fireflies", 1988, "japanese"),
        ("Drive My Car", 2021, "japanese"), ("Ne Zha 2", 2025, "chinese"), ("Ip Man", 2008, "cantonese"),
        ("Roma", 2018, "spanish"), ("Cinema Paradiso", 1988, "italian"), ("Amelie", 2001, "french"),
        ("Life Is Beautiful", 1997, "italian"), ("Perfect Days", 2023, "japanese"),
    ],
    # other series (K-drama, anime, Turkish, Spanish ...)
    "os": [
        ("Squid Game", 2021, "korean"), ("Money Heist", 2017, "spanish"), ("Dark", 2017, "german"),
        ("Crash Landing on You", 2019, "korean"), ("Alice in Borderland", 2020, "japanese"),
        ("Lupin", 2021, "french"), ("Elite", 2018, "spanish"), ("Vincenzo", 2021, "korean"),
        ("All of Us Are Dead", 2022, "korean"), ("Hellbound", 2021, "korean"), ("The Glory", 2022, "korean"),
        ("Attack on Titan", 2013, "japanese"), ("Death Note", 2006, "japanese"),
        ("Demon Slayer Kimetsu no Yaiba", 2019, "japanese"), ("Naruto", 2002, "japanese"),
        ("Fullmetal Alchemist Brotherhood", 2009, "japanese"), ("Jujutsu Kaisen", 2020, "japanese"),
        ("One Piece", 1999, "japanese"), ("Kingdom", 2019, "korean"), ("Itaewon Class", 2020, "korean"),
        ("Goblin", 2016, "korean"), ("Extraordinary Attorney Woo", 2022, "korean"),
        ("Business Proposal", 2022, "korean"), ("My Love from the Star", 2013, "korean"),
        ("Kurulus Osman", 2019, "turkish"), ("Dirilis Ertugrul", 2014, "turkish"),
        ("Hunter x Hunter", 2011, "japanese"), ("Cowboy Bebop", 1998, "japanese"),
    ],
}
SEED_GROUP = {"bm": "bolly", "bs": "bolly", "sm": "south", "om": "other", "os": "other"}


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
    if not country:  # only the language is known
        if primary in SOUTH:
            return "south", primary
        if primary == "hindi":
            return "bolly", "hindi"
    if primary == "english" or (not primary and western) or (western and "english" in langs):
        return "holly", "english"
    return "other", primary


# ---- loading
_pools: dict = {}      # pool -> (valid until, items)
_locks: dict = {}      # pool -> lock (one load at a time)
_genres: dict = {}     # genre -> (valid until, items)
_meta: dict = {}       # imdb id -> (valid until, {"country", "language"})
_index: dict = {}      # imdb id -> item (for the buttons, which only carry the id)
_cats: dict = {}       # section -> (valid until, items) for the sections that use SEEDS
_cat_locks: dict = {}  # section -> lock
_seed_cache: dict = {}  # (kind, name, year) -> (valid until, item or None)
_seed_gate = asyncio.Semaphore(6)


def _fresh(entry) -> bool:
    return bool(entry) and entry[0] > time.time()


def _friendly(title: str) -> str:
    """'Pushpa 2: The Rule' -> 'Pushpa 2 The Rule' (a colon in a word would break the file search)."""
    return re.sub(r"\s+", " ", re.sub(r"[:;!?\"\u201c\u201d]", " ", title or "")).strip()


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
        item["title"] = _friendly(item["title"])
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
            info = None
            for attempt in (1, 2):  # one retry: a single hiccup should not hide a title
                try:
                    info = await _meta_of(kind, item["id"])
                    break
                except Exception:
                    await asyncio.sleep(0.4)
            if info is None:
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
            if enrich:
                log.info("Trending pool %s: %s titles, groups %s", name, len(items),
                         dict(Counter(i.get("group") for i in items)))
        return items


# ---- curated titles
async def _resolve_seed(key: str, kind: str, name: str, year, lang: str):
    """A curated title -> a real item (id, rating, poster ...) from Cinemeta, or None."""
    ck = (kind, name, year)
    hit = _seed_cache.get(ck)
    if _fresh(hit):
        item = hit[1]
    else:
        try:
            async with _seed_gate:
                url = URL(f"{CINEMETA}/catalog/{kind}/top/search={quote(name, safe='')}.json", encoded=True)
                data = await _get_json(url, timeout=8)
        except Exception as e:
            log.info("Curated title '%s' could not be looked up (%s)", name, e)
            return None  # not remembered: it is tried again next time
        best, best_score = None, 0.0
        for m in (data or {}).get("metas") or []:
            if not isinstance(m, dict):
                continue
            cand = _cm_item(m, kind)
            if not cand["title"] or not cand["id"] or len(cand["id"]) > 40:
                continue
            score = moviedb._score(name, str(year), cand["title"], cand.get("year", ""))
            if score > best_score:
                best, best_score = cand, score
        item = best if (best and best_score >= 0.7) else None
        if len(_seed_cache) > 3000:
            _seed_cache.clear()
        _seed_cache[ck] = (time.time() + (3 * 86400 if item else 3600), item)
    if not item:
        return None
    item = dict(item)
    item["title"] = name  # the curated name is written the way files are named, so tapping it finds the file
    item["group"], item["lang"] = SEED_GROUP[key], lang
    return item


async def _seeded_category(key: str, spec) -> list:
    """Titles that are popular right now first, then the curated titles until the section is full."""
    hit = _cats.get(key)
    if _fresh(hit):
        return hit[1]
    lock = _cat_locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cats.get(key)
        if _fresh(hit):
            return hit[1]
        kind, pool, want, limit = spec
        items = await _pool(pool)
        out = [i for i in items if i.get("group") in want][:limit]
        have = {i["id"] for i in out}
        seeds = SEEDS.get(key, [])
        pos = 0
        while len(out) < limit and pos < len(seeds):
            take = seeds[pos:pos + (limit - len(out)) + 4]
            pos += len(take)
            found = await asyncio.gather(*(_resolve_seed(key, kind, *s) for s in take), return_exceptions=True)
            for it in found:
                if isinstance(it, dict) and it["id"] not in have and len(out) < limit:
                    have.add(it["id"])
                    out.append(it)
        if out:
            for it in out:
                _index[it["id"]] = it
            # a full list is kept for the normal time, a short one (Cinemeta had a hiccup) only for 10 minutes
            _cats[key] = (time.time() + (_ttl() if len(out) >= limit else 600), out)
            log.info("Trending section %s: %s titles", key, len(out))
        return out


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
    if key in SEEDS:
        return await _seeded_category(key, spec)
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
    if key in SEEDS:
        return _fresh(_cats.get(key))
    spec = CATS.get(key)
    return bool(spec) and _fresh(_pools.get(spec[1]))


def find_item(item_id: str):
    it = _index.get(item_id)
    if it:
        return it
    for _until, items in _cats.values():  # curated titles (the index may have been cleared)
        for x in items:
            if x["id"] == item_id:
                return x
    return None


async def warm():
    """Loads the big lists in the background (called when the bot starts)."""
    for name in ("mt", "st", "mr", "sr"):
        try:
            await _pool(name)
        except Exception as e:
            log.warning("Trending warm-up of %s failed: %s", name, e)
    for key in SEEDS:
        try:
            await get_category(key)
        except Exception as e:
            log.warning("Trending warm-up of section %s failed: %s", key, e)
    counts = {k: len(_pools[name][1]) for k, name in (("movies", "mt"), ("series", "st")) if name in _pools}
    log.info("Trending lists ready: %s", counts)
