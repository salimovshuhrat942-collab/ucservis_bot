# Video Tools Bot — Telegram video utility bot + admin panel

Production-ready aiogram 3.x bot that turns any video into a Telegram Video
Note, plus 12 other FFmpeg-powered tools, with a full FastAPI admin panel.

## Stack

- Python 3.12+, aiogram 3.x (async, FSM)
- FFmpeg / ffprobe (subprocess, non-blocking)
- SQLAlchemy 2.0 async ORM — SQLite by default, one env var away from PostgreSQL
- FastAPI + Jinja2 admin panel (JWT cookie auth)
- APScheduler for periodic temp-file cleanup

## Features implemented

**User-facing (bot):**
Video→Video Note (3 quality tiers) · Compressor (3 levels) · Trimmer (FSM time
input) · Speed 0.5x–3x · Remove audio · Extract MP3 · GIF creator · Circular
profile video · Reverse · Resize (Reels/TikTok/Shorts/Telegram/Square) ·
Thumbnail · Watermark (text or logo overlay) · Video info · Queue with
premium fast-lane · Single-message progress editing (Downloading→Processing→
Uploading→Done) · Uzbek/Russian/English i18n · Referral system (+1 premium
conversion per invite, leaderboard) · Forced-join (multi-channel) · Admin
`/admin` quick stats in-chat.

**Admin panel (`/admin`):** dashboard (users/premium/conversions/CPU/RAM/disk/
queue), user manager (search, ban/unban, premium toggle, delete), required
channels (add/remove/activate/reorder), feature toggles, global settings
(upload limits, FFmpeg preset, welcome messages, referral reward, maintenance
mode…), action logs, text broadcast (photo/video/animation/document supported
in `broadcast_worker.py`, wire up more form fields as needed).

## What's scaffolded vs. what needs your finishing touch

This is a real, runnable codebase, not pseudocode — but a system this size
needs a few things wired to *your* environment before go-live:

- **Batch mode**: `handlers/states.py` has `BatchStates` ready; the bot
  currently processes one video per upload, which is what most users want
  for video-note conversion. Wire the `/batch` command to loop over uploads
  into `BatchStates.collecting` if you want true multi-file batches.
- **GIF/circular params**: currently fixed defaults (first 5s, 12fps for GIF;
  10s cap for circular). Easy to add a duration-picker keyboard the same way
  `trim` collects start/end.
- **Multi-role admin accounts**: `AdminUser` table + bcrypt login path exists
  in `admin/main.py`; only the single `.env` owner login is wired to a UI —
  add a "create admin" form if you want moderator/admin accounts from the UI.
- **Broadcast media types**: the worker supports photo/video/animation/
  document; the template only exposes a text box. Add file inputs + a
  local-file-id upload step if you need it from the UI.

## Local setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN, OWNER_ID, ADMIN_PANEL_PASSWORD...

# run bot and admin panel in two terminals
python main.py
python run_admin.py
```

Requires `ffmpeg` + `ffprobe` on PATH (`apt install ffmpeg` / `brew install ffmpeg`).

Admin panel: http://localhost:8000/admin — login `owner` / your `ADMIN_PANEL_PASSWORD`.

## Deployment

### Docker / VPS
```bash
docker compose up -d --build
```
Runs bot + admin panel in one container (`entrypoint.sh` starts both
processes). Admin panel on port 8000 — put nginx/Caddy in front for TLS.

### Railway
Push this repo, Railway auto-detects `railway.json` → builds the
`Dockerfile` → runs `entrypoint.sh` (both bot + panel in one service). Set
env vars from `.env.example` in the Railway dashboard. Expose port 8000 for
the admin panel under Settings → Networking.

### Render
`render.yaml` included — Render will build the Dockerfile as a Web Service.
Set the required env vars (BOT_TOKEN, OWNER_ID, ADMIN_PANEL_PASSWORD,
ADMIN_PANEL_SECRET) as secrets in the dashboard.

### Switching to PostgreSQL
Just change `DATABASE_URL` in `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
```
Tables auto-create on startup (`init_db()` in both `main.py` and
`admin/main.py`) — no manual migration needed for a fresh DB. For
schema changes on an existing DB, add Alembic migrations (already in
`requirements.txt`).

## Project structure

```
config/        settings.py (.env → pydantic), constants.py (feature enums, presets)
database/      models.py (SQLAlchemy), db.py (engine/session), crud.py (all queries)
handlers/      start.py, video.py (upload + 13 features + queue submission), admin_commands.py
keyboards/     inline.py (all inline keyboards)
middlewares/   db session injection, throttling, forced-join
services/      ffmpeg_service.py (all FFmpeg ops), queue_service.py, job_store.py
utils/         i18n.py, progress.py (single-message progress editor), filesystem.py
locales/       uz.json, ru.json, en.json
admin/         FastAPI app (main.py, auth.py, broadcast_worker.py) + templates/
main.py        bot entrypoint
run_admin.py   admin panel entrypoint
```

## Security notes

- Change `ADMIN_PANEL_SECRET` and `ADMIN_PANEL_PASSWORD` before deploying —
  defaults in `.env.example` are placeholders only.
- Rate limiting: `ThrottlingMiddleware` drops updates faster than 0.5s/user;
  tune in `main.py`.
- All uploaded/processed files are written to per-user temp dirs and deleted
  immediately after each job (see `finally:` block in `handlers/video.py`);
  a scheduled sweep also clears anything older than 1h.
- Filenames are never taken from user input — always `uuid4`-based
  (`utils/filesystem.safe_name`).
