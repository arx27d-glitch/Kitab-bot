"""Trending list + movie ratings for the MOVIE HUB bot (used by bot.py).

* /trending  : top 10 trending movies + top 10 trending series, each with a rating.
               The list comes from TMDB (themoviedb.org), the IMDb rating from OMDb (omdbapi.com).
               Both keys are free. Without OMDB_API_KEY the TMDB rating is shown instead.
* file rating: when a file is sent, the rating of its movie/series is added to the caption.

Nothing here can break the bot: every network error is caught and the rating is simply left out.
No extra pip package is needed (urllib runs in a thread). Settings are read from the environment
when they are used, so the order of load_dotenv() does not matter.
"""
import asyncio
import difflib
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import NamedTuple, Optional

log = logging.getLogger("bookbot")

LINE = "━━━━━━━━━━━━━━━━━━"
TMDB_URL = "https://api.themoviedb.org/3"
OMDB_URL = "https://www.omdbapi.com/"
USER_AGENT = "Mozilla/5.0 (compatible; MovieHubBot/1.0)"


# ----------------------------------------------------------------------------
# SETTINGS (environment variables, see .env.example)
# ----------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except ValueError:
        return default


def tmdb_key() -> str:
    return _env("TMDB_API_KEY")


def omdb_key() -> str:
    return _env("OMDB_API_KEY")


def trending_enabled() -> bool:
    return bool(tmdb_key())


def file_rating_enabled() -> bool:
    """Rating line in the file caption: needs a key, and FILE_RATING must not be false."""
    return bool(tmdb_key() or omdb_key()) and _env("FILE_RATING", "true").lower() in ("1", "true", "yes")


# ----------------------------------------------------------------------------
# HTTP (standard library only)
# ----------------------------------------------------------------------------
class ApiError(Exception):
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status} {body}".strip())
        self.status = status
        self.body = body


def _http_get(url: str, headers: dict, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:  # keep the url (it has the key) out of the error text
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise ApiError(e.code, body) from None


async def _tmdb(path: str, **params):
    key = tmdb_key()
    if not key:
        raise ApiError(0, "TMDB_API_KEY is not set")
    headers = {}
    if key.startswith("eyJ"):  # the long "API Read Access Token" works too
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
    url = f"{TMDB_URL}{path}?{urllib.parse.urlencode(params)}"
    return await asyncio.to_thread(_http_get, url, headers, 8)


_omdb_pause_until = 0.0


async def _omdb(**params) -> Optional[dict]:
    """OMDb answer as a dict, or None (no key, not found, daily limit, network problem)."""
    global _omdb_pause_until
    key = omdb_key()
    if not key or time.time() < _omdb_pause_until:
        return None
    params["apikey"] = key
    url = f"{OMDB_URL}?{urllib.parse.urlencode(params)}"
    try:
        data = await asyncio.to_thread(_http_get, url, {}, 8)
    except ApiError as e:
        if e.status == 401:  # free key = 1000 requests/day; a wrong key also gives 401
            _omdb_pause_until = time.time() + 3600
            log.warning("OMDb refused the request (%s). IMDb ratings paused for 1 hour, TMDB rating is used.", e.body[:80])
        return None
    except Exception as e:
        log.warning("OMDb request failed: %s: %s", type(e).__name__, e)
        return None
    return data if str(data.get("Response")) == "True" else None


def _num(value) -> Optional[float]:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None  # "N/A"
    return number if number > 0 else None


def _tmdb_rating(row: dict) -> Optional[float]:
    """TMDB vote average, only when enough people voted (a new release has 0 votes)."""
    votes = row.get("vote_count") or 0
    vote = row.get("vote_average") or 0
    return round(float(vote), 1) if votes >= 5 and vote > 0 else None


def esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


# ----------------------------------------------------------------------------
# TEXTS of /trending in every bot language (en = fallback)
# ----------------------------------------------------------------------------
_KEYS = ("t_title", "t_movies", "t_series", "t_hint", "t_wait", "t_fail")
_TT = {
    "en": ("Trending Now", "Top {n} Movies", "Top {n} Series",
           "Send the name of any title to get its file.", "Fetching the trending list...",
           "Couldn't fetch the trending list right now. Please try again later."),
    "hi": ("अभी ट्रेंडिंग", "टॉप {n} मूवीज़", "टॉप {n} सीरीज़",
           "फ़ाइल पाने के लिए किसी भी टाइटल का नाम भेजें।", "ट्रेंडिंग लिस्ट ला रहा हूँ...",
           "अभी ट्रेंडिंग लिस्ट नहीं मिल पाई, कृपया बाद में कोशिश करें।"),
    "fa": ("ترندهای الان", "{n} فیلم برتر", "{n} سریال برتر",
           "برای دریافت فایل، نام هر عنوان را بفرست.", "در حال دریافت لیست ترندها...",
           "الان نمی‌توانم لیست ترندها را بگیرم، لطفاً بعداً دوباره تلاش کن."),
    "uz": ("Hozir trendda", "Top {n} film", "Top {n} serial",
           "Fayl olish uchun istalgan nomni yuboring.", "Trend ro'yxati olinmoqda...",
           "Hozir trend ro'yxatini olib bo'lmadi, keyinroq urinib ko'ring."),
    "ru": ("Сейчас в тренде", "Топ-{n} фильмов", "Топ-{n} сериалов",
           "Отправь название любого фильма, чтобы получить файл.", "Загружаю список трендов...",
           "Сейчас не удалось получить список трендов, попробуй позже."),
    "es": ("Tendencias ahora", "Top {n} películas", "Top {n} series",
           "Envía el nombre de cualquier título para recibir su archivo.", "Obteniendo la lista de tendencias...",
           "No se pudo obtener la lista de tendencias ahora, inténtalo más tarde."),
    "ar": ("الأكثر رواجاً الآن", "أفضل {n} أفلام", "أفضل {n} مسلسلات",
           "أرسل اسم أي عنوان للحصول على ملفه.", "جارٍ جلب قائمة الأكثر رواجاً...",
           "تعذّر جلب القائمة الآن، حاول لاحقاً."),
    "tr": ("Şu An Trend Olanlar", "En İyi {n} Film", "En İyi {n} Dizi",
           "Dosyasını almak için herhangi bir başlığın adını gönder.", "Trend listesi getiriliyor...",
           "Trend listesi şu an alınamadı, lütfen sonra tekrar dene."),
    "vi": ("Đang thịnh hành", "Top {n} phim", "Top {n} series",
           "Gửi tên bất kỳ phim nào để nhận tệp.", "Đang lấy danh sách thịnh hành...",
           "Hiện chưa lấy được danh sách thịnh hành, vui lòng thử lại sau."),
    "uk": ("Зараз у тренді", "Топ-{n} фільмів", "Топ-{n} серіалів",
           "Надішли назву будь-якого фільму, щоб отримати файл.", "Завантажую список трендів...",
           "Зараз не вдалося отримати список трендів, спробуй пізніше."),
    "id": ("Sedang Tren", "{n} Film Teratas", "{n} Serial Teratas",
           "Kirim nama judul apa pun untuk mendapatkan filenya.", "Mengambil daftar tren...",
           "Daftar tren belum bisa diambil sekarang, coba lagi nanti."),
    "ms": ("Sedang Tular", "{n} Filem Teratas", "{n} Siri Teratas",
           "Hantar nama mana-mana tajuk untuk mendapatkan failnya.", "Mendapatkan senarai tular...",
           "Senarai tular tidak dapat diambil sekarang, cuba lagi nanti."),
    "ko": ("지금 인기 급상승", "인기 영화 TOP {n}", "인기 시리즈 TOP {n}",
           "원하는 제목을 보내면 파일을 받을 수 있어요.", "인기 목록을 불러오는 중...",
           "지금은 인기 목록을 가져오지 못했어요. 나중에 다시 시도하세요."),
    "pt": ("Em alta agora", "Top {n} filmes", "Top {n} séries",
           "Envie o nome de qualquer título para receber o arquivo.", "Buscando a lista de tendências...",
           "Não foi possível obter a lista de tendências agora, tente mais tarde."),
    "zh": ("当前热门", "热门电影 Top {n}", "热门剧集 Top {n}",
           "发送任意片名即可获取文件。", "正在获取热门榜单...",
           "暂时无法获取热门榜单，请稍后再试。"),
    "fr": ("Tendances du moment", "Top {n} films", "Top {n} séries",
           "Envoie le nom d'un titre pour recevoir son fichier.", "Récupération de la liste des tendances...",
           "Impossible de récupérer la liste des tendances pour l'instant, réessaie plus tard."),
    "de": ("Gerade im Trend", "Top {n} Filme", "Top {n} Serien",
           "Sende den Namen eines Titels, um die Datei zu erhalten.", "Trendliste wird geladen...",
           "Die Trendliste konnte gerade nicht geladen werden, versuche es später."),
    "it": ("Di tendenza ora", "Top {n} film", "Top {n} serie",
           "Invia il nome di un titolo per ricevere il file.", "Recupero la lista dei trend...",
           "Impossibile recuperare la lista dei trend ora, riprova più tardi."),
    "he": ("הכי חם עכשיו", "{n} הסרטים המובילים", "{n} הסדרות המובילות",
           "שלח את שם הכותר כדי לקבל את הקובץ.", "מביא את רשימת הטרנדים...",
           "לא ניתן להביא את רשימת הטרנדים כרגע, נסה שוב מאוחר יותר."),
    "nl": ("Nu trending", "Top {n} films", "Top {n} series",
           "Stuur de naam van een titel om het bestand te krijgen.", "Trendlijst ophalen...",
           "De trendlijst kon nu niet worden opgehaald, probeer het later opnieuw."),
    "sv": ("Trendar just nu", "Topp {n} filmer", "Topp {n} serier",
           "Skicka namnet på en titel för att få filen.", "Hämtar trendlistan...",
           "Kunde inte hämta trendlistan just nu, försök igen senare."),
}
TT = {code: dict(zip(_KEYS, texts)) for code, texts in _TT.items()}


def t(lang: str, key: str, **values) -> str:
    text = TT.get(lang, {}).get(key) or TT["en"][key]
    return text.format(**values) if values else text


# ----------------------------------------------------------------------------
# /trending : top movies + top series of the week
# ----------------------------------------------------------------------------
_trend = {"ts": 0.0, "data": None}
_trend_lock: Optional[asyncio.Lock] = None


async def _trend_item(kind: str, row: dict) -> dict:
    """One trending title with its best rating (IMDb through OMDb, else TMDB)."""
    date = (row.get("release_date") or row.get("first_air_date") or "")[:4]
    item = {
        "title": row.get("title") or row.get("name") or "?",
        "year": date if date.isdigit() else "",
        "kind": kind,
        "tmdb_id": row.get("id"),
        "imdb_id": None,
        "rating": _tmdb_rating(row),
        "source": "TMDB",
    }
    if omdb_key() and row.get("id"):
        try:
            ext = await _tmdb(f"/{kind}/{row['id']}/external_ids")
            imdb_id = ext.get("imdb_id") or None
            if imdb_id:
                item["imdb_id"] = imdb_id
                found = await _omdb(i=imdb_id)
                imdb = _num(found.get("imdbRating")) if found else None
                if imdb:
                    item["rating"], item["source"] = imdb, "IMDb"
        except Exception as e:
            log.warning("IMDb rating of %s failed: %s: %s", item["title"], type(e).__name__, e)
    return item


async def _top(kind: str) -> list:
    window = "day" if _env("TRENDING_WINDOW", "week").lower() == "day" else "week"
    count = min(max(_env_int("TRENDING_COUNT", 10), 1), 20)
    data = await _tmdb(f"/trending/{kind}/{window}", language="en-US")
    rows = [r for r in (data.get("results") or []) if not r.get("adult")][:count]
    gate = asyncio.Semaphore(5)

    async def one(row):
        async with gate:
            return await _trend_item(kind, row)

    done = await asyncio.gather(*(one(r) for r in rows), return_exceptions=True)
    return [d for d in done if isinstance(d, dict)]


async def get_trending(force: bool = False) -> dict:
    """{"movies": [...], "series": [...]}. Cached (TRENDING_CACHE_MIN, default 6 hours)."""
    global _trend_lock
    if _trend_lock is None:
        _trend_lock = asyncio.Lock()
    ttl = max(_env_int("TRENDING_CACHE_MIN", 360), 1) * 60

    def fresh():
        return _trend["data"] and time.time() - _trend["ts"] < ttl

    if not force and fresh():
        return _trend["data"]
    async with _trend_lock:
        if not force and fresh():
            return _trend["data"]
        got = await asyncio.gather(_top("movie"), _top("tv"), return_exceptions=True)
        movies, series = [[] if isinstance(g, BaseException) else g for g in got]
        if not movies and not series:
            if _trend["data"]:  # an old list is better than an error
                log.warning("Trending refresh failed, showing the old list")
                return _trend["data"]
            raise next((g for g in got if isinstance(g, BaseException)), RuntimeError("empty trending list"))
        _trend["data"] = {"movies": movies, "series": series}
        _trend["ts"] = time.time()
        return _trend["data"]


def trending_text(data: dict, lang: str = "en") -> str:
    movies, series = data.get("movies") or [], data.get("series") or []
    sources = {i["source"] for i in movies + series if i.get("rating")}
    mixed = len(sources) > 1
    lines = [f"🔥 <b>{t(lang, 't_title')}</b>", LINE]
    for icon, key, items in (("🎬", "t_movies", movies), ("📺", "t_series", series)):
        if not items:
            continue
        lines.append(f"{icon} <b>{t(lang, key, n=len(items))}</b>")
        for n, item in enumerate(items, 1):
            year = f" ({item['year']})" if item.get("year") else ""
            if item.get("rating"):
                rate = f"⭐ {item['rating']:.1f}"
                if mixed and item["source"] != "IMDb":
                    rate += f" ({item['source']})"
            else:
                rate = "⭐ N/A"
            lines.append(f"{n}. <b>{esc(item['title'])}</b>{year} ┃ {rate}")
        lines.append("")
    if sources == {"IMDb"}:
        credit = "Data: TMDB • Ratings: IMDb"
    elif sources == {"TMDB"}:
        credit = "Data and ratings: TMDB"
    else:
        credit = "Data: TMDB • Ratings: IMDb / TMDB"
    lines += [LINE, f"♤ <i>{t(lang, 't_hint')}</i>", f"<i>{credit}</i>"]
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# FILE NAME -> movie name + year
# "KGF.Chapter.2.2022.1080p.WEB-DL.Hindi.x264.mkv" -> ("KGF Chapter 2", "2022", movie)
# ----------------------------------------------------------------------------
class Parsed(NamedTuple):
    key: str
    title: str
    year: Optional[str]
    series: bool


_VIDEO_OR_NO_EXT = re.compile(r"\.(mkv|mp4|avi|mov|webm|m4v|ts|flv|wmv|mpg|mpeg|3gp)$", re.I)
_OTHER_EXT = re.compile(r"\.(pdf|epub|mobi|azw3|docx?|odt|pptx?|txt|rtf|zip|rar|7z|mp3|m4a|ogg|wav|flac|apk|exe)$", re.I)
_RES = re.compile(r"^\d{3,4}p$")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_SEASON = re.compile(r"^(?:s\d{1,2}(?:e\d{1,3})?|s\d{1,2}s\d{1,2}|e\d{1,3}|ep\d{1,3}|episodes?|seasons?\d{0,2})$")
_HARD = set(
    "4k 8k uhd hdrip webrip webdl webhd hdtv hdtc hdts hdcam cam camrip predvd dvdrip dvdscr dvd bluray "
    "bdrip brrip bdremux remux x264 x265 h264 h265 hevc avc xvid 10bit hdr hdr10 hdr10plus dolbyvision "
    "aac aac2 aac20 ac3 dts atmos esub esubs hsub hsubs imax proper repack extended uncut unrated remastered "
    "amzn nf dsnp hmax atvp hotstar zee5 sonyliv jiocinema hulu".split()
)
_SOFT = set(
    "hindi english tamil telugu malayalam kannada bengali bangla marathi punjabi gujarati bhojpuri urdu "
    "odia oriya dual dualaudio multi multiaudio org dubbed dub subbed sub subs audio".split()
)


def _key(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def parse_title(filename: str) -> Optional[Parsed]:
    """Movie/series name, release year and series flag from a file name (None = not a movie file)."""
    name = (filename or "").strip()
    if not name or _OTHER_EXT.search(name):
        return None
    name = _VIDEO_OR_NO_EXT.sub("", name)
    name = re.sub(r"https?://\S+|www\.\S+", " ", name)
    name = re.sub(r"@\w+", " ", name)
    name = re.sub(r"\[\s*((?:19|20)\d{2})\s*\]", r" \1 ", name)  # [2022] is a year, other [tags] are dropped
    name = re.sub(r"\[[^\]]*\]", " ", name)
    name = re.sub(r"[._]+", " ", name)
    if " " not in name.strip() and name.count("-") >= 2:  # Movie-Name-2022-1080p-WEB-DL
        name = name.replace("-", " ")
    name = re.sub(r"[()\[\]{}:;,|\"“”]+", " ", name)
    name = re.sub(r"(?i)\bweb[\s\-]?(dl|rip|hd)\b", lambda m: "web" + m.group(1), name)
    name = re.sub(r"(?i)\bblu[\s\-]?ray\b", "bluray", name)
    name = re.sub(r"(?i)\bhd[\s\-]?(rip|tv|cam|ts|tc)\b", lambda m: "hd" + m.group(1), name)
    name = re.sub(r"(?i)\bdvd[\s\-]?(rip|scr)\b", lambda m: "dvd" + m.group(1), name)
    name = re.sub(r"(?i)\bdual[\s\-]?audio\b", "dualaudio", name)
    name = re.sub(r"(?i)\bmulti[\s\-]?audio\b", "multiaudio", name)
    name = re.sub(r"\b(?:[A-Za-z]\s){2,}[A-Za-z]\b", lambda m: m.group(0).replace(" ", ""), name)  # K G F -> KGF

    tokens = [tok.strip("-") for tok in name.split()]
    tokens = [tok for tok in tokens if tok]
    if not tokens:
        return None
    keys = [_key(tok) for tok in tokens]
    series = any(_SEASON.match(k) for k in keys)
    # first quality / source / season word ends the name (the very first word always belongs to the name)
    hard = next(
        (i for i, k in enumerate(keys) if i >= 1 and (k in _HARD or _RES.match(k) or _SEASON.match(k))),
        len(tokens),
    )
    window, wkeys = tokens[:hard], keys[:hard]
    max_year = datetime.now().year + 1
    year_at = [i for i, k in enumerate(wkeys) if i >= 1 and _YEAR.match(k) and int(k) <= max_year]
    year = None
    if year_at:  # the LAST year is the release year ("Wonder Woman 1984 2020", "Blade Runner 2049 2017")
        year = wkeys[year_at[-1]]
        title_tokens = window[: year_at[-1]]
        while len(title_tokens) > 1 and _key(title_tokens[-1]) in _SOFT:  # "KGF 2 Hindi 2022"
            title_tokens.pop()
    else:
        soft = next((i for i, k in enumerate(wkeys) if i >= 1 and k in _SOFT), len(window))
        title_tokens = window[:soft]
    title = " ".join(title_tokens[:10]).strip(" -")
    slug = _slug(title)
    if len(slug) < 2 or re.fullmatch(r"file \d+", slug):
        return None
    return Parsed(f"{'tv' if series else 'mv'}|{slug}|{year or ''}", title, year, series)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _sim(a: str, b: str) -> float:
    """0..1 similarity of two names (letters and digits only)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 4 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


# ----------------------------------------------------------------------------
# RATING OF A FILE (TMDB search -> imdb id -> OMDb), cached in memory
# ----------------------------------------------------------------------------
_rcache: dict = {}  # key -> (expires_at, info or None)
_inflight: dict = {}  # key -> running lookup
MIN_SIM = 0.72


def _remember(key: str, info: Optional[dict], ttl: float):
    if len(_rcache) > 4000:
        now = time.time()
        for k in [k for k, v in _rcache.items() if v[0] < now]:
            _rcache.pop(k, None)
        if len(_rcache) > 4000:
            _rcache.clear()
    _rcache[key] = (time.time() + ttl, info)


def _cached(key: str):
    """(found, info): found=False when there is no fresh cache entry."""
    hit = _rcache.get(key)
    if hit and hit[0] > time.time():
        return True, hit[1]
    return False, None


def _pick(rows: list, title: str, year: Optional[str]) -> Optional[dict]:
    """Best TMDB search result: the name must really look like the file name (a wrong rating is worse than none)."""
    want = _slug(title).replace(" ", "")
    best, best_score = None, 0.0
    for row in rows[:6]:
        names = (row.get("title") or row.get("name"), row.get("original_title") or row.get("original_name"))
        sim = max((_sim(want, _slug(n).replace(" ", "")) for n in names if n), default=0.0)
        if sim < MIN_SIM:
            continue
        date = (row.get("release_date") or row.get("first_air_date") or "")[:4]
        score = sim
        if year and date.isdigit():
            score += 0.25 if date == year else (-0.1 if abs(int(date) - int(year)) > 1 else 0)
        if score > best_score + 1e-9:  # a tie keeps the more relevant (earlier) result
            best, best_score = row, score
    return best


async def _tmdb_search(kind: str, title: str, year: Optional[str]) -> Optional[dict]:
    params = {"query": title, "include_adult": "false", "language": "en-US"}
    if year:
        params["year" if kind == "movie" else "first_air_date_year"] = year
    hit = _pick((await _tmdb(f"/search/{kind}", **params)).get("results") or [], title, year)
    if not hit and year:  # the year in the file name can be wrong
        params.pop("year", None)
        params.pop("first_air_date_year", None)
        hit = _pick((await _tmdb(f"/search/{kind}", **params)).get("results") or [], title, year)
    return hit


async def _complete(kind: str, row: dict) -> dict:
    date = (row.get("release_date") or row.get("first_air_date") or "")[:4]
    info = {
        "name": row.get("title") or row.get("name") or "",
        "year": date if date.isdigit() else "",
        "kind": kind,
        "tmdb_id": row.get("id"),
        "imdb_id": None,
        "rating": _tmdb_rating(row),
        "source": "TMDB",
    }
    if omdb_key():
        try:
            imdb_id = (await _tmdb(f"/{kind}/{row['id']}/external_ids")).get("imdb_id") or None
        except Exception:
            imdb_id = None
        if imdb_id:
            info["imdb_id"] = imdb_id
            found = await _omdb(i=imdb_id)
            imdb = _num(found.get("imdbRating")) if found else None
            if imdb:
                info["rating"], info["source"] = imdb, "IMDb"
    return info


async def _omdb_by_title(title: str, year: Optional[str], series: bool) -> Optional[dict]:
    """Used when there is no TMDB key (or TMDB found nothing): OMDb title lookup."""
    kinds = ("series", "movie") if series else ("movie", "series")
    tries = [(kinds[0], year), (kinds[0], None), (kinds[1], None)] if year else [(kinds[0], None), (kinds[1], None)]
    want = _slug(title).replace(" ", "")
    for typ, yr in tries:
        params = {"t": title, "type": typ}
        if yr:
            params["y"] = yr
        data = await _omdb(**params)
        if data and _sim(want, _slug(data.get("Title")).replace(" ", "")) >= MIN_SIM:
            return {
                "name": data.get("Title") or title,
                "year": (data.get("Year") or "")[:4],
                "kind": "tv" if typ == "series" else "movie",
                "tmdb_id": None,
                "imdb_id": data.get("imdbID"),
                "rating": _num(data.get("imdbRating")),
                "source": "IMDb",
            }
    return None


async def _find(p: Parsed) -> Optional[dict]:
    info = None
    if tmdb_key():
        for kind in (("tv", "movie") if p.series else ("movie", "tv")):
            row = await _tmdb_search(kind, p.title, p.year)
            if row:
                info = await _complete(kind, row)
                break
    if not (info and info.get("rating")) and omdb_key():
        info = await _omdb_by_title(p.title, p.year, p.series) or info
    return info if info and info.get("rating") else None


async def _lookup_uncached(p: Parsed) -> Optional[dict]:
    try:
        info = await _find(p)
    except Exception as e:  # network problem: try again soon
        log.warning("Rating lookup for %r failed: %s: %s", p.title, type(e).__name__, e)
        _remember(p.key, None, 300)
        return None
    _remember(p.key, info, 3 * 86400 if info else 3600)
    return info


def _task_for(p: Parsed) -> "asyncio.Future":
    task = _inflight.get(p.key)
    if task is None:
        task = asyncio.ensure_future(_lookup_uncached(p))
        _inflight[p.key] = task
        task.add_done_callback(lambda _t, k=p.key: _inflight.pop(k, None))
    return task


async def lookup(p: Parsed) -> Optional[dict]:
    found, info = _cached(p.key)
    if found:
        return info
    return await asyncio.shield(_task_for(p))  # shield: a timeout of one user must not stop the lookup


async def warm(filename: str):
    """Looks the rating up so caption_line() can use it. Waits RATING_TIMEOUT seconds at most. Never raises."""
    try:
        if not file_rating_enabled():
            return
        p = parse_title(filename)
        if p:
            await asyncio.wait_for(lookup(p), timeout=_env_float("RATING_TIMEOUT", 4.0))
    except Exception:
        pass  # includes the timeout: the file is sent without a rating, the lookup goes on in the background


def prefetch(filenames):
    """Starts lookups for the titles on a result page (at most RATING_PREFETCH different ones), so the
    rating is already cached when the user taps a file. Never raises."""
    try:
        if not file_rating_enabled():
            return
        limit, seen = max(_env_int("RATING_PREFETCH", 2), 0), set()
        for name in filenames:
            p = parse_title(name)
            if not p or p.key in seen:
                continue
            seen.add(p.key)
            if len(seen) > limit:
                break
            if not _cached(p.key)[0]:
                _task_for(p)
    except Exception:
        pass


def caption_line(filename: str) -> str:
    """Rating line for the file caption (from the cache only, so it is instant). "" when unknown."""
    try:
        if not file_rating_enabled():
            return ""
        p = parse_title(filename)
        if not p:
            return ""
        found, info = _cached(p.key)
        if not (found and info and info.get("rating")):
            return ""
        if info.get("imdb_id"):
            link = f"https://www.imdb.com/title/{info['imdb_id']}/"
        else:
            link = f"https://www.themoviedb.org/{'tv' if info['kind'] == 'tv' else 'movie'}/{info['tmdb_id']}"
        year = f" ({info['year']})" if info.get("year") else ""
        return f'⭐ <a href="{link}">{info["source"]}</a> <b>{info["rating"]:.1f}</b>/10 ┃ {esc(info["name"])[:60]}{year}\n'
    except Exception:
        return ""
