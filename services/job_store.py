from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class JobContext:
    token: str
    user_id: int
    chat_id: int
    input_path: Path
    file_size: int
    is_premium: bool
    created_at: float = field(default_factory=time.time)
    # transient params collected across steps (trim start, watermark text, etc.)
    params: dict = field(default_factory=dict)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, JobContext] = {}

    def create(self, user_id: int, chat_id: int, input_path: Path, file_size: int, is_premium: bool) -> JobContext:
        token = uuid.uuid4().hex[:10]
        ctx = JobContext(token=token, user_id=user_id, chat_id=chat_id,
                          input_path=input_path, file_size=file_size, is_premium=is_premium)
        self._jobs[token] = ctx
        return ctx

    def get(self, token: str) -> Optional[JobContext]:
        return self._jobs.get(token)

    def drop(self, token: str) -> None:
        self._jobs.pop(token, None)

    def cleanup_older_than(self, seconds: int = 3600) -> None:
        now = time.time()
        stale = [t for t, j in self._jobs.items() if now - j.created_at > seconds]
        for t in stale:
            self._jobs.pop(t, None)


job_store = JobStore()
