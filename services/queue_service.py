"""
Two-lane priority queue: premium jobs go into a fast lane processed by
QUEUE_WORKERS_PREMIUM workers, regular jobs into the normal lane.
Each job is a coroutine factory (callable returning an awaitable) so the
queue stays generic and reusable for every feature.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from config.settings import settings

logger = logging.getLogger("queue_service")


@dataclass
class Job:
    job_id: str
    user_id: int
    label: str
    coro_factory: Callable[[], Awaitable[None]]
    is_premium: bool = False


class VideoQueue:
    def __init__(self) -> None:
        self.normal_q: asyncio.Queue[Job] = asyncio.Queue()
        self.premium_q: asyncio.Queue[Job] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._active_jobs: dict[str, Job] = {}

    def size(self) -> int:
        return self.normal_q.qsize() + self.premium_q.qsize()

    async def start(self) -> None:
        for _ in range(settings.QUEUE_WORKERS):
            self._workers.append(asyncio.create_task(self._worker(self.normal_q)))
        for _ in range(settings.QUEUE_WORKERS_PREMIUM):
            self._workers.append(asyncio.create_task(self._worker(self.premium_q)))
        logger.info("Queue started with %d workers", len(self._workers))

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()

    async def submit(self, user_id: int, label: str, coro_factory: Callable[[], Awaitable[None]],
                      is_premium: bool = False) -> str:
        job = Job(job_id=str(uuid.uuid4()), user_id=user_id, label=label,
                  coro_factory=coro_factory, is_premium=is_premium)
        target = self.premium_q if is_premium else self.normal_q
        await target.put(job)
        return job.job_id

    async def _worker(self, q: asyncio.Queue) -> None:
        while True:
            job = await q.get()
            self._active_jobs[job.job_id] = job
            try:
                await job.coro_factory()
            except Exception:
                logger.exception("Job %s failed", job.job_id)
            finally:
                self._active_jobs.pop(job.job_id, None)
                q.task_done()


video_queue = VideoQueue()
