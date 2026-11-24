# 🎬 MOVIE HUB Bot (Telegram)

Movie/Series ka **naam** bhejo, bot file dhoond kar bhej deta hai. Poster, rating, trailer, trending list, request system aur premium plan ke saath.

> ⚠️ Is bot me sirf wahi files daalo jinke rights tumhare paas hain (apni files, public domain, free/legal content).

## Features
- **Poster + rating** search result par, `/info naam` se poori detail (plot, cast, trailer, IMDb link)
- **Free movie-info API** (koi key nahi): Cinemeta → TVmaze → IMDb suggestion. Ek band ho to agla chalta hai. TMDB use nahi hota
- **/trending**: popular movies, popular series, top rated. Title par tap karo to bot me search ho jata hai
- **Exact naam pehle**: "Money Heist" likho to sirf Money Heist ki files, "Money Heist Korea" nahi (`EXACT_FIRST`)
- **Request system**: file na mile to "Request" button. Admin file daale to user ko apne aap message jata hai
- **Premium plan**: `/addpremium`, daily limit, premium ki files auto-delete nahi hoti
- 4+ force-join channels (10 tak), 5 min auto-delete + "dobara bhejo" button
- Quality / language / season filters, pagination, 21 languages
- Admin: `/stats /broadcast /index /diag /logs /ban /sent /requests /premiums` aur bahut kuch (`/help` me poori list)
- Sab settings environment variables se

## Setup
1. **Bot banao**: @BotFather se token lo.
2. **API ID / HASH**: https://my.telegram.org se lo.
3. **DB channel** (private) banao, bot ko usme **admin** banao, saari files post karo.
4. **Force-join channels** me bhi bot ko **admin** banao.
5. **MongoDB** (Atlas free) ka `MONGO_URI` lo, warna Railway restart par data mit sakta hai.
6. `.env.example` copy karke `.env` banao (ya Railway Variables me `railway.env` ke naam daalo).

## Naye variables
| Variable | Matlab |
|---|---|
| `POSTER_ON_SEARCH` | `true` = search par poster + rating |
| `INFO_TIMEOUT` | info API ka max intezaar (default `3.5` sec) |
| `OMDB_API_KEY` | optional, omdbapi.com ki free key |
| `EXACT_FIRST` | `true` = exact naam wali files pehle/sirf wahi |
| `FUZZY_SEARCH` | `true` = kuch na mile to related titles bhi |
| `REQUEST_LIMIT` | ek user ki max pending requests |
| `FREE_DAILY_LIMIT` | free user ki roz ki limit, `0` = unlimited |
| `PREMIUM_NO_AUTODELETE` | premium ki files delete na ho |
| `PREMIUM_SKIP_JOIN` | premium ko channel join na karna pade |

Purane variables (`API_ID`, `BOT_TOKEN`, `DB_CHANNEL`, `ADMINS`, `CHANNEL_n`, `AUTO_DELETE_SECONDS` ...) pehle jaise hi hain.

## Premium kaise do
```
/addpremium 123456789 30     -> 30 din
/addpremium @username 7      -> 7 din
(user ke message par reply) /addpremium 30
/delpremium 123456789
/premiums
```
User `/myplan` se apna plan dekhta hai. `FREE_DAILY_LIMIT=10` karoge to free user roz 10 files le payega, premium unlimited.

## Run
```bash
pip install -r requirements.txt
python bot.py
```

### Docker
```bash
docker build -t movie-bot .
docker run -d --env-file .env -v $(pwd)/data:/data -e DB_PATH=/data/files.db movie-bot
```

### Railway / Heroku / Render / VPS
Repo connect karo, dashboard me variables daalo. Start command: `python bot.py`

## GitHub par upload
`.env` aur `*.session` file `.gitignore` me hain, isliye token/secrets GitHub par **nahi** jayenge. Kabhi `.env` commit mat karna.

## Dhyan rakhne wali baatein
- Auto-delete timers bot restart par reset ho jate hain.
- Bot start karne se pehle jo files DB channel me thi, wo `/index full` se index hoti hain.
- `/diag` chalao: wo database, channels, movie-info API aur file bhejna sab check karke batata hai.
- Info API (Cinemeta etc.) free aur unofficial hai. Kabhi down ho to bot bina poster ke normal chalta hai.
