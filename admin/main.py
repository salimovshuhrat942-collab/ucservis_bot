from __future__ import annotations

import datetime as dt
from pathlib import Path

import psutil
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from admin.auth import create_token, decode_token, COOKIE_NAME
from config.settings import settings
from database import crud
from database.db import get_session, init_db
from services.queue_service import video_queue
from utils.filesystem import human_size

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Video Bot Admin Panel")
app.mount("/admin/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
async def on_startup():
    await init_db()


def current_admin(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_token(token)


async def require_admin(request: Request):
    admin = current_admin(request)
    if not admin:
        raise HTTPException(status_code=307, headers={"Location": "/admin/login"})
    return admin


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------

@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/admin/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    # Simple owner login via .env password; extend with AdminUser table for multi-role accounts.
    if username == "owner" and password == settings.ADMIN_PANEL_PASSWORD:
        token = create_token(username, role="owner")
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=12 * 3600)
        return resp

    async with get_session() as session:
        admin_row = await crud.get_admin_by_username(session, username)
    if admin_row:
        from passlib.hash import bcrypt
        if bcrypt.verify(password, admin_row.password_hash):
            token = create_token(username, role=admin_row.role)
            resp = RedirectResponse(url="/admin", status_code=302)
            resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=12 * 3600)
            return resp

    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})


@app.get("/admin/logout")
async def logout():
    resp = RedirectResponse(url="/admin/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        total = await crud.count_users(session)
        since_today = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        since_week = dt.datetime.utcnow() - dt.timedelta(days=7)
        since_month = dt.datetime.utcnow() - dt.timedelta(days=30)
        today = await crud.count_users_since(session, since_today)
        week = await crud.count_users_since(session, since_week)
        month = await crud.count_users_since(session, since_month)
        premium = await crud.count_premium_users(session)
        conversions_today = await crud.count_conversions_today(session)
        top_feature = await crud.most_used_feature(session) or "—"

    disk = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory()

    ctx = {
        "request": request, "admin": admin,
        "total": total, "today": today, "week": week, "month": month,
        "premium": premium, "conversions_today": conversions_today, "top_feature": top_feature,
        "queue_size": video_queue.size(),
        "cpu": cpu, "ram_percent": ram.percent, "ram_used": human_size(ram.used), "ram_total": human_size(ram.total),
        "disk_percent": disk.percent, "disk_used": human_size(disk.used), "disk_total": human_size(disk.total),
    }
    return templates.TemplateResponse("dashboard.html", ctx)


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------

@app.get("/admin/users", response_class=HTMLResponse)
async def users_page(request: Request, q: str = "", admin: dict = Depends(require_admin)):
    async with get_session() as session:
        users = await crud.search_users(session, q) if q else await crud.list_users(session, limit=100)
    return templates.TemplateResponse("users.html", {"request": request, "admin": admin, "users": users, "q": q})


@app.post("/admin/users/{user_id}/ban")
async def ban_user(user_id: int, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.set_ban(session, user_id, True)
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/unban")
async def unban_user(user_id: int, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.set_ban(session, user_id, False)
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/premium_on")
async def premium_on(user_id: int, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.set_premium(session, user_id, True)
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/premium_off")
async def premium_off(user_id: int, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.set_premium(session, user_id, False)
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/delete")
async def delete_user_route(user_id: int, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.delete_user(session, user_id)
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


# ---------------------------------------------------------------------
# Required channels
# ---------------------------------------------------------------------

@app.get("/admin/channels", response_class=HTMLResponse)
async def channels_page(request: Request, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        channels = await crud.list_channels(session)
        forced_join_enabled = (await crud.get_setting(session, "forced_join_enabled", "1")) == "1"
    return templates.TemplateResponse("channels.html", {
        "request": request, "admin": admin, "channels": channels, "forced_join_enabled": forced_join_enabled,
    })


@app.post("/admin/channels/add")
async def add_channel_route(chat_id: str = Form(...), title: str = Form(""), invite_link: str = Form(""),
                             admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.add_channel(session, chat_id.strip(), title.strip(), invite_link.strip() or None)
        await session.commit()
    return RedirectResponse(url="/admin/channels", status_code=302)


@app.post("/admin/channels/{channel_id}/remove")
async def remove_channel_route(channel_id: int, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.remove_channel(session, channel_id)
        await session.commit()
    return RedirectResponse(url="/admin/channels", status_code=302)


@app.post("/admin/channels/{channel_id}/toggle")
async def toggle_channel_route(channel_id: int, active: bool = Form(...), admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.toggle_channel(session, channel_id, active)
        await session.commit()
    return RedirectResponse(url="/admin/channels", status_code=302)


@app.post("/admin/channels/forced_join_toggle")
async def forced_join_toggle(enabled: bool = Form(...), admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.set_setting(session, "forced_join_enabled", "1" if enabled else "0")
        await session.commit()
    return RedirectResponse(url="/admin/channels", status_code=302)


# ---------------------------------------------------------------------
# Feature manager
# ---------------------------------------------------------------------

@app.get("/admin/features", response_class=HTMLResponse)
async def features_page(request: Request, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        features = await crud.get_enabled_features(session)
    return templates.TemplateResponse("features.html", {"request": request, "admin": admin, "features": features})


@app.post("/admin/features/{feature}/toggle")
async def toggle_feature_route(feature: str, enabled: bool = Form(...), admin: dict = Depends(require_admin)):
    async with get_session() as session:
        await crud.set_feature_toggle(session, feature, enabled)
        await session.commit()
    return RedirectResponse(url="/admin/features", status_code=302)


# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------

@app.get("/admin/settings", response_class=HTMLResponse)
async def settings_page(request: Request, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        all_settings = await crud.get_all_settings(session)
    return templates.TemplateResponse("settings.html", {"request": request, "admin": admin, "settings": all_settings})


@app.post("/admin/settings")
async def settings_save(request: Request, admin: dict = Depends(require_admin)):
    form = await request.form()
    async with get_session() as session:
        for key, value in form.items():
            await crud.set_setting(session, key, str(value))
        await session.commit()
    return RedirectResponse(url="/admin/settings", status_code=302)


# ---------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------

@app.get("/admin/logs", response_class=HTMLResponse)
async def logs_page(request: Request, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        logs = await crud.recent_logs(session, limit=200)
    return templates.TemplateResponse("logs.html", {"request": request, "admin": admin, "logs": logs})


# ---------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------

@app.get("/admin/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request, admin: dict = Depends(require_admin)):
    async with get_session() as session:
        history = await crud.recent_broadcasts(session)
    return templates.TemplateResponse("broadcast.html", {"request": request, "admin": admin, "history": history})


@app.post("/admin/broadcast/send")
async def broadcast_send(request: Request, message: str = Form(""), admin: dict = Depends(require_admin)):
    from admin.broadcast_worker import run_broadcast
    async with get_session() as session:
        users = await crud.list_users(session, limit=100000)
    user_ids = [u.id for u in users]
    sent, failed, blocked = await run_broadcast(user_ids, text=message)
    async with get_session() as session:
        await crud.add_broadcast_log(session, admin_id=0, content_type="text", sent=sent, failed=failed, blocked=blocked)
        await session.commit()
    return RedirectResponse(url="/admin/broadcast", status_code=302)
