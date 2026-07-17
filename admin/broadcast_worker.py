from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest

from config.settings import settings


async def run_broadcast(user_ids: list[int], text: str = "", photo: str | None = None,
                         video: str | None = None, animation: str | None = None,
                         document: str | None = None) -> tuple[int, int, int]:
    """Sends a broadcast to all given user ids. file params are Telegram file_ids or local paths.
    Returns (sent, failed, blocked)."""
    bot = Bot(token=settings.BOT_TOKEN)
    sent = failed = blocked = 0
    try:
        for uid in user_ids:
            try:
                if photo:
                    await bot.send_photo(uid, photo, caption=text or None)
                elif video:
                    await bot.send_video(uid, video, caption=text or None)
                elif animation:
                    await bot.send_animation(uid, animation, caption=text or None)
                elif document:
                    await bot.send_document(uid, document, caption=text or None)
                else:
                    await bot.send_message(uid, text)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                failed += 1
            except TelegramBadRequest:
                failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)  # ~20 msg/sec, stays under Telegram limits
    finally:
        await bot.session.close()
    return sent, failed, blocked
