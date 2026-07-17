from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import settings
from database.db import init_db
from handlers import start, video, admin_commands
from middlewares.db_middleware import DbSessionMiddleware
from middlewares.forced_join import ForcedJoinMiddleware
from middlewares.throttling import ThrottlingMiddleware
from services.queue_service import video_queue
from services.job_store import job_store
from utils.filesystem import cleanup_old_temp_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("main")


async def main() -> None:
    await init_db()

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares (order matters: db session first, then throttling, then forced join).
    # Registered explicitly on message + callback_query (rather than the generic
    # "update" observer) so event_from_user/event_chat are guaranteed to be
    # populated when each middleware runs.
    db_mw = DbSessionMiddleware()
    throttle_mw = ThrottlingMiddleware(min_interval=0.5)
    join_mw = ForcedJoinMiddleware(bot)

    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(db_mw)
        observer.outer_middleware(throttle_mw)
        observer.outer_middleware(join_mw)

    dp.include_router(start.router)
    dp.include_router(video.router)
    dp.include_router(admin_commands.router)

    await video_queue.start()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_old_temp_files, "interval", minutes=30, kwargs={"max_age_seconds": 3600})
    scheduler.add_job(job_store.cleanup_older_than, "interval", minutes=30, kwargs={"seconds": 3600})
    scheduler.start()

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await video_queue.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
