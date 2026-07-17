from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, CallbackQuery, Message

from database import crud
from keyboards.inline import forced_join_keyboard
from utils.i18n import t


class ForcedJoinMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session = data.get("session")
        user = data.get("event_from_user")
        if session is None or user is None:
            return await handler(event, data)

        # Allow the "check subscription" callback and /start through unconditionally
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)

        enabled = (await crud.get_setting(session, "forced_join_enabled", "1")) == "1"
        if not enabled:
            return await handler(event, data)

        channels = await crud.list_channels(session, active_only=True)
        if not channels:
            return await handler(event, data)

        lang = data["db_user"].language if data.get("db_user") else "uz"
        not_joined = []
        for ch in channels:
            try:
                member = await self.bot.get_chat_member(ch.chat_id, user.id)
                if member.status in ("left", "kicked"):
                    not_joined.append(ch)
            except Exception:
                not_joined.append(ch)

        if not_joined:
            kb = forced_join_keyboard(not_joined, lang)
            text = t(lang, "not_subscribed")
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb)
            elif isinstance(event, CallbackQuery):
                await event.answer(t(lang, "still_not_subscribed"), show_alert=True)
            return  # block handler

        return await handler(event, data)
