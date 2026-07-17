from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """Simple in-memory rate limiter: min interval between updates per user."""

    def __init__(self, min_interval: float = 0.7):
        self.min_interval = min_interval
        self._last_call: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            now = time.monotonic()
            last = self._last_call.get(user.id, 0)
            if now - last < self.min_interval:
                return  # silently drop, avoid spam replies
            self._last_call[user.id] = now
        return await handler(event, data)
