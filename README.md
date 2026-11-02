# 📚 Kitab Bot (Telegram)

Ek Telegram bot jo kitab ka **naam** bhejne par file dhoond kar bhej deta hai.

## Features
- 4 channel **force-join** (zarurat ho to 10 tak badha sakte ho)
- `/start`, `/help` commands
- File bhejne ke **5 minute baad auto-delete** (time env se change hota hai)
- Naam se search + pagination buttons
- Admin commands: `/stats`, `/broadcast`
- Sab settings environment variables se

> ⚠️ Is bot me sirf wahi files daalo jinke rights tumhare paas hain (apni files, public domain, free/legal content).

## Setup

1. **Bot banao**: @BotFather se token lo.
2. **API ID / HASH**: https://my.telegram.org se lo.
3. **DB channel banao** (private) aur bot ko usme **admin** banao. Isme saari kitabon ki files post karo. Bot unhe apne aap index kar lega.
4. **4 force-join channels** me bhi bot ko **admin** banao (warna join check nahi hoga).
5. `.env.example` ko copy karke `.env` banao aur sab values bharo:

```bash
cp .env.example .env
```

| Variable | Matlab |
|---|---|
| `API_ID`, `API_HASH` | my.telegram.org se |
| `BOT_TOKEN` | @BotFather se |
| `DB_CHANNEL` | Files wale channel ka id (`-100...`) |
| `ADMINS` | Admin user ids (space se alag) |
| `CHANNEL_1` ... `CHANNEL_4` | Force-join channel (`@username` ya `-100...` id) |
| `CHANNEL_n_LINK` | Private channel ka invite link |
| `AUTO_DELETE_SECONDS` | `300` = 5 minute, `0` = band |
| `BOT_NAME`, `OWNER_USERNAME`, `SUPPORT_USERNAME`, `UPDATES_CHANNEL` | Buttons aur naam |
| `START_TEXT`, `JOIN_TEXT` | Messages badalne ke liye (optional) |

## Run

```bash
pip install -r requirements.txt
python bot.py
```

### Docker
```bash
docker build -t kitab-bot .
docker run -d --env-file .env -v $(pwd)/data:/data -e DB_PATH=/data/files.db kitab-bot
```

### Heroku / Railway / Render / VPS
Repo connect karo aur dashboard me upar wale environment variables daalo. Start command: `python bot.py`

## GitHub par upload

```bash
git init
git add .
git commit -m "Kitab bot"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

`.env` aur `*.session` file `.gitignore` me hain, isliye tumhare token/secrets GitHub par **nahi** jayenge. Kabhi `.env` commit mat karna.

## Dhyan rakhne wali baatein
- Auto-delete bot chalu rehne tak hi kaam karta hai. Restart par pending delete timers reset ho jate hain.
- Bot start karne se pehle jo files DB channel me thi, wo index nahi hongi. Unhe dobara post/forward karo.
- Agar kisi force-join channel me bot admin nahi hai, to bot log me error dega aur us channel ko skip kar dega.
