"""Movie / series info from FREE APIs (no API key needed) + helpers that clean file names.

TMDB is NOT used any more. The providers are tried in this order and the first good answer wins.
A provider that errors out is skipped for a few minutes (circuit breaker), so the bot never hangs.

  1. OMDb       only if OMDB_API_KEY is set (free key from https://www.omdbapi.com/apikey.aspx) - optional
  2. Cinemeta   Stremio's IMDb based catalog (no key)  -> poster, rating, plot, cast, trailer, trending lists
  3. TVmaze     TV series (no key)
  4. IMDb suggestion  title, year, poster, cast (no key)

Public functions
  lookup(query, min_score)  -> dict with title/year/rating/genres/plot/cast/poster/trailer ... or None
  trending(kind, catalog)   -> list of popular / top rated titles (cached for 1 hour)
  clean_title(file_name)    -> "KGF Chapter 2 (2022) 1080p Hindi.mkv" -> "KGF Chapter 2"
  title_key(text)           -> lower-case comparable key of a clean title (used for exact matching)
  fetch_image(url)          -> BytesIO of a poster (used when Telegram can't fetch the url itself)
"""
import asyncio
import html
import io
import logging
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import quote

import aiohttp
from yarl import URL

from translit import to_latin

log = logging.getLogger("bookbot.moviedb")

CINEMETA = "https://v3-cinemeta.strem.io"
TVMAZE = "https://api.tvmaze.com"
IMDB_SUGGEST = "https://v3.sg.media-imdb.com/suggestion"
OMDB = "https://www.omdbapi.com/"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
GOOD_ENOUGH = 0.85  # stop asking more providers when a match is at least this good
_THIS_YEAR = time.gmtime().tm_year


# ----------------------------------------------------------------------------
# FILE NAME CLEANING
# ----------------------------------------------------------------------------
_EXT = re.compile(
    r"\.(?:mkv|mp4|avi|mov|webm|m4v|ts|flv|wmv|mpg|mpeg|3gp|mp3|m4a|flac|wav|ogg|pdf|epub|zip|rar|7z|srt)$",
    re.I,
)
_SITE_WWW = re.compile(r"^\s*www\.[a-z0-9-]+\.[a-z]{2,6}\b[\s._-]*", re.I)
_SITE_TLD = re.compile(
    r"^\s*[a-z0-9][a-z0-9-]*\.(?:com|net|org|xyz|vip|cc|pw|club|ink|ws|info|link)\b[\s._-]*", re.I
)
_PRE = [
    (re.compile(r"\bweb[\s._-]?(?:dl|rip|hd)\b", re.I), " webdl "),
    (re.compile(r"\bweb[\s._-]?series\b", re.I), " "),
    (re.compile(r"\bblu[\s._-]?ray\b", re.I), " bluray "),
    (re.compile(r"\bhd[\s._-]?(?:rip|cam|ts|tc)\b", re.I), " hdrip "),
]
_JUNK_WORDS = {
    # source / quality
    "hd", "fhd", "uhd", "hq", "webdl", "webrip", "hdrip", "brrip", "bdrip", "bluray", "dvdrip", "dvdscr",
    "hdtv", "hdcam", "camrip", "hdts", "hdtc", "pdtv", "predvd", "remux", "amzn", "dsnp", "hmax", "zee5",
    "hotstar", "sonyliv",
    # codec / audio
    "x264", "x265", "h264", "h265", "hevc", "avc", "xvid", "10bit", "8bit", "hdr", "hdr10", "atmos",
    # languages / audio tags
    "hindi", "hin", "english", "eng", "tamil", "tam", "telugu", "tel", "malayalam", "kannada", "bengali",
    "bangla", "marathi", "punjabi", "gujarati", "bhojpuri", "urdu", "odia", "oriya", "dual", "multi",
    "dubbed", "org",
    # subs / release tags
    "esub", "esubs", "msub", "sub", "subs", "subtitle", "subtitles", "proper", "repack", "extended",
    "uncut", "unrated", "imax", "remastered", "complete", "season", "episode", "episodes",
}
_JUNK_RE = re.compile(
    r"(?:\d{3,4}p|\d{3,4}x\d{3,4}|4k|"
    r"s\d{1,2}(?:e\d{1,3})?(?:-?e?\d{1,3})?|"
    r"e\d{1,3}|ep\d{1,3}|season\d{0,2}|"
    r"(?:19|20)[0-3]\d|"
    r"\d+(?:\.\d+)?(?:gb|mb)|"
    r"(?:dd|ddp|aac|ac3|eac3|dts)\d*)"
)


def _simplify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@lru_cache(maxsize=50000)
def clean_title(name: str) -> str:
    """The movie / series name of a file name (or of a search text):
    'Money.Heist.S01E01.720p.WEB-DL.Hindi.mkv' -> 'Money Heist'."""
    s = _EXT.sub("", (name or "").strip())
    s = re.sub(r"\[[^\]]*\]|\{[^}]*\}|\([^)]*\)", " ", s)  # [tags] {tags} (2022)
    s = re.sub(r"@\w+", " ", s)  # @channel
    s = _SITE_WWW.sub("", s)
    s = _SITE_TLD.sub("", s)
    for rx, rep in _PRE:
        s = rx.sub(rep, s)
    s = re.sub(r"[._\-+,:;|~]+", " ", s)
    out = []
    for i, tok in enumerate(s.split()):
        low = tok.lower()
        if i > 0 and (low in _JUNK_WORDS or _JUNK_RE.fullmatch(low)):
            break  # everything after the first quality / language / year / season tag is not the name
        out.append(tok)
    return " ".join(out)


@lru_cache(maxsize=50000)
def title_key(text: str) -> str:
    """Comparable form of a clean title: 'Money.Heist.S01E01.720p.mkv' and 'money heist' give the same key."""
    t = clean_title(text or "")
    if not t.isascii():
        t = to_latin(t)
    return _simplify(t)


def year_in(text: str) -> str:
    """A release year (1900 - next year) found in a file name / query, else ''.
    '2012 (2009) 720p' -> 2009, '1917.2019.1080p' -> 2019, 'Blade Runner 2049' -> ''."""
    t = re.sub(r"\d{3,4}p", " ", text or "", flags=re.I)
    found = re.findall(r"\(\s*((?:19|20)[0-3]\d)\s*\)", t) or re.findall(r"(?<!\d)((?:19|20)[0-3]\d)(?!\d)", t)
    found = [y for y in found if int(y) <= _THIS_YEAR + 1]
    return found[-1] if found else ""


# ----------------------------------------------------------------------------
# HTTP + circuit breaker
# ----------------------------------------------------------------------------
_session = None
_down: dict = {}  # provider -> time until it is skipped


def _sess() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(headers={"User-Agent": UA, "Accept": "application/json"})
    return _session


async def close():
    """Closes the HTTP session (called when the bot stops)."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def _get_json(url, params=None, timeout: float = 6.0):
    async with _sess().get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        if r.status == 404:  # "nothing found" is an answer, not an error
            return None
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return await r.json(content_type=None)


def _is_down(name: str) -> bool:
    return _down.get(name, 0) > time.time()


def _mark_down(name: str, why: str, secs: int = 180):
    _down[name] = time.time() + secs
    log.warning("Movie info provider '%s' skipped for %ss (%s)", name, secs, why)


def _omdb_key() -> str:
    return os.environ.get("OMDB_API_KEY", "").strip()


def status() -> dict:
    """{'cinemeta': 'ok', 'tvmaze': 'down 120s', ...} for /diag."""
    now = time.time()
    names = (["omdb"] if _omdb_key() else []) + ["cinemeta", "tvmaze", "imdb"]
    return {n: ("ok" if not _is_down(n) else f"down {int(_down[n] - now)}s") for n in names}


# ----------------------------------------------------------------------------
# One info record (all providers fill the same keys)
# ----------------------------------------------------------------------------
def _info(**kw) -> dict:
    d = {
        "id": "", "imdb_id": "", "ext": "", "title": "", "year": "", "type": "movie", "rating": "",
        "genres": [], "runtime": "", "plot": "", "cast": [], "director": [], "poster": "", "trailer": "",
        "source": "", "score": 0.0,
    }
    d.update({k: v for k, v in kw.items() if v is not None and v != ""})
    return d


def _year(value) -> str:
    m = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return m.group(0) if m else ""


def _listify(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in value if str(v).strip() and str(v).strip().upper() != "N/A"]


def _clean(value) -> str:
    value = "" if value is None else str(value).strip()
    return "" if value.upper() == "N/A" else value


def _poster(url) -> str:
    url = _clean(url)
    if not url.startswith("http"):
        return ""
    return url.replace("/poster/small/", "/poster/medium/")


def _yt(value) -> str:
    value = str(value or "")
    return f"https://www.youtube.com/watch?v={value}" if re.fullmatch(r"[\w-]{6,15}", value) else ""


def _score(q: str, qyear: str, title: str, year: str) -> float:
    """0..1 : how well a title matches what the user typed."""
    a, b = _simplify(q), _simplify(title)
    if not a or not b:
        return 0.0
    if a == b:
        s = 1.0
    else:
        s = SequenceMatcher(None, a, b).ratio()
        ta, tb = set(a.split()), set(b.split())
        if ta and ta <= tb:  # every typed word is in the title ("kgf" in "KGF Chapter 2")
            s = max(s, 0.80 + 0.10 * len(ta) / len(tb))
    if qyear and year:
        s += 0.10 if str(year)[:4] == str(qyear) else -0.10
    return max(0.0, min(1.0, s))


# ----------------------------------------------------------------------------
# PROVIDER: Cinemeta (Stremio) - no key
# ----------------------------------------------------------------------------
def _cm_item(m: dict, kind: str) -> dict:
    imdb = str(m.get("imdb_id") or m.get("id") or "")
    return _info(
        id=imdb,
        imdb_id=imdb if imdb.startswith("tt") else "",
        title=_clean(m.get("name")),
        year=_year(m.get("year") or m.get("releaseInfo")),
        type="series" if (m.get("type") or kind) == "series" else "movie",
        rating=_clean(m.get("imdbRating")),
        genres=_listify(m.get("genres") or m.get("genre")),
        runtime=_clean(m.get("runtime")),
        plot=_clean(m.get("description")),
        cast=_listify(m.get("cast")),
        director=_listify(m.get("director")),
        poster=_poster(m.get("poster")),
        source="Cinemeta",
    )


async def _p_cinemeta(q: str, year: str) -> list:
    qs = quote(q, safe="")
    urls = [
        URL(f"{CINEMETA}/catalog/{kind}/top/search={qs}.json", encoded=True) for kind in ("movie", "series")
    ]
    results = await asyncio.gather(*(_get_json(u) for u in urls), return_exceptions=True)
    if all(isinstance(r, Exception) for r in results):
        raise results[0]
    out = []
    for kind, r in zip(("movie", "series"), results):
        if isinstance(r, Exception) or not isinstance(r, dict):
            continue
        for m in (r.get("metas") or [])[:8]:
            if isinstance(m, dict):
                out.append(_cm_item(m, kind))
    return out


async def _cm_enrich(info: dict) -> dict:
    """The catalog entry is short: the meta page has the full plot, cast and trailer."""
    if not info.get("imdb_id"):
        return info
    url = URL(f"{CINEMETA}/meta/{info['type']}/{info['imdb_id']}.json", encoded=True)
    data = await _get_json(url)
    m = (data or {}).get("meta") or {}
    links = [x for x in (m.get("links") or []) if isinstance(x, dict)]

    def by_cat(cat):
        return [x.get("name") for x in links if x.get("category") == cat and x.get("name")]

    info = dict(info)
    plot = _clean(m.get("description"))
    if plot:
        info["plot"] = plot
    for key, val in (
        ("cast", _listify(m.get("cast")) or _listify(by_cat("Cast"))),
        ("director", _listify(m.get("director")) or _listify(by_cat("Directors"))),
        ("genres", _listify(m.get("genres") or m.get("genre")) or _listify(by_cat("Genres"))),
    ):
        if val:
            info[key] = val
    for key, val in (
        ("runtime", _clean(m.get("runtime"))),
        ("rating", _clean(m.get("imdbRating"))),
        ("poster", _poster(m.get("poster"))),
        ("year", _year(m.get("year") or m.get("releaseInfo"))),
    ):
        if val:
            info[key] = val
    for t in m.get("trailers") or []:
        link = _yt(t.get("source")) if isinstance(t, dict) else ""
        if link:
            info["trailer"] = link
            break
    if not info.get("trailer"):
        for t in m.get("trailerStreams") or []:
            link = _yt(t.get("ytId")) if isinstance(t, dict) else ""
            if link:
                info["trailer"] = link
                break
    return info


# ----------------------------------------------------------------------------
# PROVIDER: TVmaze (series) - no key
# ----------------------------------------------------------------------------
async def _p_tvmaze(q: str, year: str) -> list:
    data = await _get_json(f"{TVMAZE}/search/shows", params={"q": q})
    out = []
    for row in (data or [])[:8]:
        s = (row or {}).get("show") or {}
        if not s.get("name"):
            continue
        imdb = _clean((s.get("externals") or {}).get("imdb"))
        img = s.get("image") or {}
        rating = (s.get("rating") or {}).get("average")
        mins = s.get("averageRuntime") or s.get("runtime")
        out.append(
            _info(
                id=imdb or f"tvm{s.get('id')}",
                imdb_id=imdb,
                ext=str(s.get("id") or ""),
                title=s["name"],
                year=_year(s.get("premiered")),
                type="series",
                rating=f"{float(rating):.1f}" if rating else "",
                genres=_listify(s.get("genres")),
                runtime=f"{mins} min" if mins else "",
                plot=html.unescape(re.sub(r"<[^>]+>", "", s.get("summary") or "")).strip(),
                poster=_poster(img.get("original") or img.get("medium")),
                source="TVmaze",
            )
        )
    return out


async def _tv_enrich(info: dict) -> dict:
    if not info.get("ext"):
        return info
    data = await _get_json(f"{TVMAZE}/shows/{info['ext']}/cast")
    names = []
    for row in data or []:
        name = ((row or {}).get("person") or {}).get("name")
        if name and name not in names:
            names.append(name)
    info = dict(info)
    if names:
        info["cast"] = names[:6]
    return info


# ----------------------------------------------------------------------------
# PROVIDER: IMDb suggestion (title, year, poster, cast) - no key
# ----------------------------------------------------------------------------
async def _p_imdb(q: str, year: str) -> list:
    low = q.lower().strip()
    first = low[0] if low and low[0].isascii() and low[0].isalnum() else "x"
    data = await _get_json(URL(f"{IMDB_SUGGEST}/{first}/{quote(low, safe='')}.json", encoded=True))
    out = []
    for d in (data or {}).get("d") or []:
        iid = str(d.get("id") or "")
        kind = str(d.get("q") or "").lower()
        if not iid.startswith("tt") or "game" in kind or "episode" in kind:
            continue
        out.append(
            _info(
                id=iid,
                imdb_id=iid,
                title=_clean(d.get("l")),
                year=_year(d.get("y")),
                type="series" if "tv series" in kind or "mini" in kind else "movie",
                cast=_listify(d.get("s")),
                poster=_poster((d.get("i") or {}).get("imageUrl")),
                source="IMDb",
            )
        )
    return out[:8]


# ----------------------------------------------------------------------------
# PROVIDER: OMDb (optional key)
# ----------------------------------------------------------------------------
async def _p_omdb(q: str, year: str) -> list:
    params = {"apikey": _omdb_key(), "t": q, "plot": "short"}
    if year:
        params["y"] = year
    d = await _get_json(OMDB, params=params)
    if not isinstance(d, dict) or d.get("Response") != "True":
        return []
    iid = _clean(d.get("imdbID"))
    return [
        _info(
            id=iid,
            imdb_id=iid,
            title=_clean(d.get("Title")),
            year=_year(d.get("Year")),
            type="series" if d.get("Type") == "series" else "movie",
            rating=_clean(d.get("imdbRating")),
            genres=_listify(d.get("Genre")),
            runtime=_clean(d.get("Runtime")),
            plot=_clean(d.get("Plot")),
            cast=_listify(d.get("Actors")),
            director=_listify(d.get("Director")),
            poster=_poster(d.get("Poster")),
            source="OMDb",
        )
    ]


def _providers():
    out = []
    if _omdb_key():
        out.append(("omdb", _p_omdb, None))
    out += [("cinemeta", _p_cinemeta, _cm_enrich), ("tvmaze", _p_tvmaze, _tv_enrich), ("imdb", _p_imdb, None)]
    return out


# ----------------------------------------------------------------------------
# LOOKUP (cached; the same question is never asked twice at the same time)
# ----------------------------------------------------------------------------
_cache: dict = {}  # key -> (valid until, info or None)
_inflight: dict = {}


def _finalize(info: dict) -> dict:
    info = dict(info)
    if not info.get("id"):
        info["id"] = "x" + format(abs(hash(info.get("title", ""))), "x")[:10]
    if info.get("imdb_id"):
        info["imdb_url"] = f"https://www.imdb.com/title/{info['imdb_id']}/"
    if not info.get("trailer"):
        info["trailer"] = "https://www.youtube.com/results?search_query=" + quote(
            f"{info.get('title', '')} {info.get('year', '')} trailer".strip()
        )
    return info


async def _resolve(q: str, year: str):
    """(best info or None, did at least one provider answer?)"""
    best, best_enrich, answered = None, None, False
    for name, search, enrich in _providers():
        if _is_down(name):
            continue
        try:
            cands = await asyncio.wait_for(search(q, year), 8)
        except Exception as e:
            _mark_down(name, f"{type(e).__name__}: {e}")
            continue
        answered = True
        cands = [c for c in cands if c.get("title")]
        for c in cands:
            c["score"] = _score(q, year, c["title"], c.get("year", ""))
        if not cands:
            continue
        cand = max(cands, key=lambda c: c["score"])
        if best is None or cand["score"] > best["score"] + 0.05:  # on a tie the earlier provider stays
            best, best_enrich = cand, enrich
        if best["score"] >= GOOD_ENOUGH:
            break
    if best is None:
        return None, answered
    if best_enrich:
        try:
            enriched = await asyncio.wait_for(best_enrich(best), 7)
            enriched["score"] = best["score"]
            best = enriched
        except Exception as e:
            log.info("Could not load the details of '%s' (%s)", best.get("title"), e)
    return _finalize(best), answered


async def _job(key, q: str, year: str):
    try:
        info, answered = await _resolve(q, year)
    except Exception as e:
        log.warning("Movie info lookup failed for '%s' (%s)", q, e)
        return None
    if info or answered:  # when every provider was down nothing is remembered
        _cache[key] = (time.time() + (43200 if info else 900), info)
        if len(_cache) > 2000:
            for k in list(_cache)[:500]:
                _cache.pop(k, None)
    return info


async def lookup(query: str, min_score: float = 0.6, timeout: float = 4.0):
    """Best match for a movie / series name (a year in the text is used as a hint), or None.

    min_score: 0.72 = the poster of a search page (must be sure), 0.45 = /info (best guess is fine)."""
    raw = (query or "").strip()
    if not raw:
        return None
    year = year_in(raw)
    q = clean_title(raw) or raw
    if not q.isascii():
        q = to_latin(q)
    if year and _simplify(q) == year:
        year = ""  # the movie "2012" is not a year hint
    key = (_simplify(q), year)
    if not key[0]:
        return None

    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        info = hit[1]
    else:
        task = _inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(_job(key, q, year))
            _inflight[key] = task
            task.add_done_callback(lambda _t, k=key: _inflight.pop(k, None))
        try:
            info = await asyncio.wait_for(asyncio.shield(task), timeout)
        except Exception:  # timeout: the job keeps running and fills the cache for the next time
            return None
    if info and info.get("score", 0) >= min_score:
        return dict(info)
    return None


# ----------------------------------------------------------------------------
# TRENDING (Cinemeta catalogs: top = popular, imdbRating = top rated)
# ----------------------------------------------------------------------------
_trend: dict = {}  # (kind, catalog) -> (valid until, items)


async def trending(kind: str = "movie", catalog: str = "top", limit: int = 40) -> list:
    key = (kind, catalog)
    hit = _trend.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        data = await _get_json(URL(f"{CINEMETA}/catalog/{kind}/{catalog}.json", encoded=True), timeout=8)
    except Exception as e:
        log.warning("Trending list (%s/%s) failed: %s", kind, catalog, e)
        return hit[1] if hit else []  # an old list is better than nothing
    items = []
    for m in (data or {}).get("metas") or []:
        if not isinstance(m, dict):
            continue
        item = _cm_item(m, kind)
        if item["title"] and item["id"] and len(item["id"]) <= 40:
            items.append(item)
        if len(items) >= limit:
            break
    if items:
        _trend[key] = (time.time() + 3600, items)
    return items


def find_trending(item_id: str):
    """An item of the trending lists that were loaded before (the buttons only carry the id)."""
    for _until, items in _trend.values():
        for it in items:
            if it["id"] == item_id:
                return it
    return None


# ----------------------------------------------------------------------------
# POSTER DOWNLOAD (fallback when Telegram can't fetch the url)
# ----------------------------------------------------------------------------
async def fetch_image(url: str, max_bytes: int = 5_000_000):
    try:
        async with _sess().get(
            url, timeout=aiohttp.ClientTimeout(total=10), headers={"Accept": "image/*"}
        ) as r:
            if r.status != 200 or not (r.content_type or "").startswith("image/"):
                return None
            data = await r.read()
    except Exception as e:
        log.info("Could not download the poster (%s)", e)
        return None
    if not data or len(data) > max_bytes:
        return None
    buf = io.BytesIO(data)
    buf.name = "poster.jpg"
    return buf
