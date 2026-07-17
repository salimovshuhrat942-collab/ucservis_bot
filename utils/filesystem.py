from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from config.settings import settings


def safe_name(prefix: str, ext: str) -> str:
    ext = ext.lstrip(".")
    ext = re.sub(r"[^a-zA-Z0-9]", "", ext) or "bin"
    return f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"


def user_temp_dir(user_id: int) -> Path:
    d = settings.temp_dir_path / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_path(*paths: Path) -> None:
    for p in paths:
        try:
            if p and p.exists():
                p.unlink()
        except Exception:
            pass


def cleanup_old_temp_files(max_age_seconds: int = 3600) -> int:
    """Delete temp files older than max_age_seconds. Returns count removed."""
    removed = 0
    root = settings.temp_dir_path
    now = time.time()
    if not root.exists():
        return 0
    for f in root.rglob("*"):
        if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
    return removed


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def parse_timecode(text: str) -> str | None:
    """Accepts mm:ss or hh:mm:ss, returns normalized ffmpeg-friendly string, or None if invalid."""
    text = text.strip()
    m = TIME_RE.match(text)
    if not m:
        return None
    a, b, c = m.groups()
    if c is None:
        return f"00:{int(a):02d}:{int(b):02d}"
    return f"{int(a):02d}:{int(b):02d}:{int(c):02d}"
