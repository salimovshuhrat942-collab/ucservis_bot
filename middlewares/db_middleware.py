from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from database import crud
from database.db import get_session


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with get_session() as session:
            data["session"] = session

            tg_user: TgUser | None = data.get("event_from_user")
            if tg_user is not None:
                user, _created = await crud.get_or_create_user(
                    session, tg_user.id, username=tg_user.username, full_name=tg_user.full_name
                )
                data["db_user"] = user

            result = await handler(event, data)
            await session.commit()
            return result
