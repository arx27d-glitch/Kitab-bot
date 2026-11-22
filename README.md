# 🎬 MOVIE Bot (Telegram) — Advanced

Movie/Series ka **naam** bhejo, bot file dhoond kar bhej deta hai.

## Features
- **Exact search**: poore shabd se match ("Money Heist" ke saath "Money Talks" nahi aata, "man" se "Batman" nahi aata). Symbols (`: , ! ? '`) ignore hote hain.
- Spelling-tolerant search (salam = salaam), Hindi/Tamil/Telugu... naam bhi (Latin me convert hokar)
- Duplicate files (same naam + size) result me sirf ek baar
- Quality / language / season filter buttons + pagination
- 4 se 10 **force-join** channels (`CHANNEL_1` ... `CHANNEL_10`, ya `/addchannel`)
- 21 languages, `/start` par language choose
- File bhejne ke baad **auto-delete** (default 5 min) + "request again" button
- `/request naam` — file na mile to user request bhej sakta hai (auto-reply group me card aata hai)
- DB channel ki files auto-index, group se auto-forward (`SOURCE_GROUPS`)
- Group me bhi kaam karta hai (bot admin ho to); group ki normal chat se fake "movie request" nahi banti
- Multi-MongoDB (`MONGO_URI`, `MONGO_URI_1` ... `MONGO_URI_10`), flood protection, ban/unban
- Admin: `/stats /broadcast /index /addchannel /delchannel /channels /setstart /delstart /admins /diag /logs /ban /unban /banned /ping /sent`
- Owner: `/addadmin /deladmin /del /dbset`

> ⚠️ Sirf wahi files daalo jinke rights tumhare paas hain.

## Setup
1. @BotFather se bot token lo, https://my.telegram.org se API ID/HASH.
2. Private **DB channel** banao, bot ko **admin** banao, files usme post karo.
3. Force-join channels me bhi bot ko **admin** banao.
4. `cp .env.example .env` karke values bharo (Railway par `railway.env` ke variables dashboard me daalo).
5. **MONGO_URI zaroor do** (mongodb.com Atlas free), warna restart par data mit jayega.

## Run
```bash
pip install -r requirements.txt
python bot.py
```
Docker: `docker build -t movie-bot . && docker run -d --env-file .env movie-bot`

Railway: repo connect karo, variables daalo (`railway.json` pehle se hai).

## Important
- Purani files ka search-text purane format me hai. Naya exact search unpar bhi chalta hai, par best result ke liye ek baar **`/index full`** chala do.
- `pyrotgfork==2.2.24.1` install na ho to `requirements.txt` me sirf `pyrotgfork` likh do.
- `FILE_TAG` default `[@OVN3RS]` hai — apna tag daalo ya khali chhodo.
- `.env` aur `*.session` kabhi commit mat karo.
- Kuch na chale to admin se `/diag` chalao.
