from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants import DEFAULT_ENABLED_FEATURES
from database.models import (
    ActionLog, AdminUser, BotSetting, BroadcastLog, FeatureToggle,
    RequiredChannel, User,
)


# ---------- Users ----------

async def get_or_create_user(
    session: AsyncSession, user_id: int, username: str | None = None,
    full_name: str | None = None, referred_by: int | None = None,
    default_language: str = "uz",
) -> tuple[User, bool]:
    user = await session.get(User, user_id)
    if user:
        user.last_seen_at = dt.datetime.utcnow()
        if username:
            user.username = username
        return user, False

    user = User(
        id=user_id,
        username=username,
        full_name=full_name,
        language=default_language,
        referred_by=referred_by if referred_by != user_id else None,
    )
    session.add(user)
    await session.flush()
    return user, True


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def set_language(session: AsyncSession, user_id: int, lang: str) -> None:
    await session.execute(update(User).where(User.id == user_id).values(language=lang))


async def increment_conversions(session: AsyncSession, user_id: int) -> None:
    user = await session.get(User, user_id)
    if user:
        user.conversions_count += 1
        if user.premium_conversions_left > 0 and not user.is_premium:
            user.premium_conversions_left -= 1


async def apply_referral_reward(session: AsyncSession, referrer_id: int, reward: int) -> None:
    referrer = await session.get(User, referrer_id)
    if referrer:
        referrer.referral_count += 1
        referrer.premium_conversions_left += reward


async def search_users(session: AsyncSession, query: str, limit: int = 50):
    q = f"%{query}%"
    stmt = select(User).where(
        (User.username.ilike(q)) | (User.full_name.ilike(q))
    )
    if query.isdigit():
        stmt = select(User).where(User.id == int(query))
    stmt = stmt.limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()


async def list_users(session: AsyncSession, offset: int = 0, limit: int = 50):
    res = await session.execute(select(User).order_by(User.registered_at.desc()).offset(offset).limit(limit))
    return res.scalars().all()


async def set_ban(session: AsyncSession, user_id: int, banned: bool) -> None:
    await session.execute(update(User).where(User.id == user_id).values(is_banned=banned))


async def set_premium(session: AsyncSession, user_id: int, premium: bool) -> None:
    await session.execute(update(User).where(User.id == user_id).values(is_premium=premium))


async def delete_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(User).where(User.id == user_id))


async def top_referrers(session: AsyncSession, limit: int = 10):
    res = await session.execute(
        select(User).where(User.referral_count > 0).order_by(User.referral_count.desc()).limit(limit)
    )
    return res.scalars().all()


# ---------- Stats ----------

async def count_users(session: AsyncSession) -> int:
    res = await session.execute(select(func.count(User.id)))
    return res.scalar_one()


async def count_users_since(session: AsyncSession, since: dt.datetime) -> int:
    res = await session.execute(select(func.count(User.id)).where(User.registered_at >= since))
    return res.scalar_one()


async def count_premium_users(session: AsyncSession) -> int:
    res = await session.execute(select(func.count(User.id)).where(User.is_premium == True))  # noqa: E712
    return res.scalar_one()


async def count_conversions_today(session: AsyncSession) -> int:
    since = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    res = await session.execute(
        select(func.count(ActionLog.id)).where(ActionLog.created_at >= since, ActionLog.result == "ok")
    )
    return res.scalar_one()


async def most_used_feature(session: AsyncSession) -> str | None:
    res = await session.execute(
        select(ActionLog.action, func.count(ActionLog.id).label("cnt"))
        .group_by(ActionLog.action).order_by(func.count(ActionLog.id).desc()).limit(1)
    )
    row = res.first()
    return row[0] if row else None


# ---------- Logs ----------

async def add_log(
    session: AsyncSession, user_id: int, action: str, username: str | None = None,
    file_size: int | None = None, result: str = "ok", error: str | None = None,
) -> None:
    session.add(ActionLog(
        user_id=user_id, username=username, action=action,
        file_size=file_size, result=result, error=error,
    ))


async def recent_logs(session: AsyncSession, limit: int = 100):
    res = await session.execute(select(ActionLog).order_by(ActionLog.created_at.desc()).limit(limit))
    return res.scalars().all()


# ---------- Required channels ----------

async def list_channels(session: AsyncSession, active_only: bool = False):
    stmt = select(RequiredChannel).order_by(RequiredChannel.order_index.asc())
    if active_only:
        stmt = stmt.where(RequiredChannel.is_active == True)  # noqa: E712
    res = await session.execute(stmt)
    return res.scalars().all()


async def add_channel(session: AsyncSession, chat_id: str, title: str = "", invite_link: str | None = None) -> RequiredChannel:
    max_order = await session.execute(select(func.max(RequiredChannel.order_index)))
    order = (max_order.scalar_one() or 0) + 1
    ch = RequiredChannel(chat_id=chat_id, title=title, invite_link=invite_link, order_index=order)
    session.add(ch)
    await session.flush()
    return ch


async def remove_channel(session: AsyncSession, channel_id: int) -> None:
    await session.execute(delete(RequiredChannel).where(RequiredChannel.id == channel_id))


async def toggle_channel(session: AsyncSession, channel_id: int, active: bool) -> None:
    await session.execute(update(RequiredChannel).where(RequiredChannel.id == channel_id).values(is_active=active))


async def reorder_channel(session: AsyncSession, channel_id: int, new_order: int) -> None:
    await session.execute(update(RequiredChannel).where(RequiredChannel.id == channel_id).values(order_index=new_order))


# ---------- Settings (KV store, drives admin-editable config) ----------

DEFAULT_SETTINGS = {
    "max_upload_mb": "200",
    "max_upload_mb_premium": "2000",
    "max_duration_sec": "600",
    "default_quality": "hd",
    "ffmpeg_preset": "veryfast",
    "compression_quality": "medium",
    "maintenance_mode": "0",
    "welcome_message_uz": "Salom! Video yuboring, men uni qayta ishlab beraman 🎬",
    "welcome_message_ru": "Привет! Отправьте видео, и я его обработаю 🎬",
    "welcome_message_en": "Hi! Send me a video and I'll process it 🎬",
    "referral_reward": "1",
    "queue_size_limit": "200",
    "forced_join_enabled": "1",
}


async def get_setting(session: AsyncSession, key: str, default: str | None = None) -> str | None:
    row = await session.get(BotSetting, key)
    if row:
        return row.value
    return DEFAULT_SETTINGS.get(key, default)


async def get_all_settings(session: AsyncSession) -> dict:
    res = await session.execute(select(BotSetting))
    rows = {r.key: r.value for r in res.scalars().all()}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(rows)
    return merged


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(BotSetting, key)
    if row:
        row.value = value
    else:
        session.add(BotSetting(key=key, value=value))


# ---------- Feature toggles ----------

async def get_enabled_features(session: AsyncSession) -> dict:
    res = await session.execute(select(FeatureToggle))
    rows = {r.feature: r.enabled for r in res.scalars().all()}
    merged = dict(DEFAULT_ENABLED_FEATURES)
    merged.update(rows)
    return merged


async def set_feature_toggle(session: AsyncSession, feature: str, enabled: bool) -> None:
    row = await session.get(FeatureToggle, feature)
    if row:
        row.enabled = enabled
    else:
        session.add(FeatureToggle(feature=feature, enabled=enabled))


# ---------- Broadcast logs ----------

async def add_broadcast_log(session: AsyncSession, admin_id: int, content_type: str, sent: int, failed: int, blocked: int) -> None:
    session.add(BroadcastLog(admin_id=admin_id, content_type=content_type, sent=sent, failed=failed, blocked=blocked))


async def recent_broadcasts(session: AsyncSession, limit: int = 20):
    res = await session.execute(select(BroadcastLog).order_by(BroadcastLog.created_at.desc()).limit(limit))
    return res.scalars().all()


# ---------- Admin panel accounts ----------

async def get_admin_by_username(session: AsyncSession, username: str) -> AdminUser | None:
    res = await session.execute(select(AdminUser).where(AdminUser.username == username))
    return res.scalar_one_or_none()
