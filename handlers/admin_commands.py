from __future__ import annotations

import datetime as dt

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from config.settings import settings
from database import crud

router = Router(name="admin_commands")


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message, session):
    if not _is_admin(message.from_user.id):
        return
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

    text = (
        "🛠 <b>Admin panel (quick view)</b>\n\n"
        f"👥 Total users: <b>{total}</b>\n"
        f"🆕 Today: <b>{today}</b>  |  Week: <b>{week}</b>  |  Month: <b>{month}</b>\n"
        f"💎 Premium: <b>{premium}</b>\n"
        f"🎬 Conversions today: <b>{conversions_today}</b>\n"
        f"🔥 Most used feature: <b>{top_feature}</b>\n\n"
        f"🌐 Full admin panel: http://localhost:{settings.ADMIN_PANEL_PORT}/admin\n"
        "(replace localhost with your server's domain/IP)"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    if not _is_admin(message.from_user.id):
        return
    await cmd_admin(message, session)
