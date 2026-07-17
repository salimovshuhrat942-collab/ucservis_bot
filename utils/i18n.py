from __future__ import annotations

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
SUPPORTED_LANGS = ["uz", "ru", "en"]

_cache: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang not in _cache:
        path = LOCALES_DIR / f"{lang}.json"
        if not path.exists():
            lang = "en"
            path = LOCALES_DIR / "en.json"
        _cache[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[lang]


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in SUPPORTED_LANGS else "en"
    data = _load(lang)
    text = data.get(key) or _load("en").get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text
