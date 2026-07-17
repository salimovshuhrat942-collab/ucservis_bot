from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest


class ProgressMessage:
    """Wraps a single Telegram message and updates it in place."""

    STAGES = {
        "uz": {"download": "⬇️ Yuklab olinmoqda...", "process": "⚙️ Qayta ishlanmoqda...",
               "upload": "⬆️ Yuklanmoqda...", "done": "✅ Tayyor!"},
        "ru": {"download": "⬇️ Скачивание...", "process": "⚙️ Обработка...",
               "upload": "⬆️ Загрузка...", "done": "✅ Готово!"},
        "en": {"download": "⬇️ Downloading...", "process": "⚙️ Processing...",
               "upload": "⬆️ Uploading...", "done": "✅ Done!"},
    }

    def __init__(self, bot: Bot, chat_id: int, message_id: int, lang: str = "uz"):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.lang = lang
        self._last_text = ""
        self._lock = asyncio.Lock()

    async def update(self, stage: str, extra: str = "") -> None:
        text = self.STAGES.get(self.lang, self.STAGES["en"]).get(stage, stage)
        if extra:
            text += f"\n{extra}"
        if text == self._last_text:
            return
        async with self._lock:
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id, message_id=self.message_id, text=text
                )
                self._last_text = text
            except TelegramBadRequest:
                pass  # message not modified / deleted, ignore

    async def error(self, message: str) -> None:
        text = f"❌ {message}"
        try:
            await self.bot.edit_message_text(chat_id=self.chat_id, message_id=self.message_id, text=text)
        except TelegramBadRequest:
            pass
