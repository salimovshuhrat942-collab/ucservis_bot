from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.constants import Feature, FEATURE_EMOJI, SPEED_OPTIONS, RESIZE_FORMATS
from utils.i18n import t


def language_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🇺🇿 O'zbekcha", callback_data="lang:uz")
    b.button(text="🇷🇺 Русский", callback_data="lang:ru")
    b.button(text="🇬🇧 English", callback_data="lang:en")
    b.adjust(1)
    return b.as_markup()


def forced_join_keyboard(channels, lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        url = ch.invite_link or f"https://t.me/{ch.chat_id.lstrip('@')}"
        b.row(InlineKeyboardButton(text=f"📢 {ch.title or ch.chat_id}", url=url))
    b.row(InlineKeyboardButton(text=t(lang, "check_subscription"), callback_data="check_sub"))
    return b.as_markup()


FEATURE_LABELS = {
    "uz": {
        Feature.VIDEO_NOTE: "Video Note qilish",
        Feature.COMPRESS: "Siqish",
        Feature.TRIM: "Qirqish",
        Feature.SPEED: "Tezlikni o'zgartirish",
        Feature.REMOVE_AUDIO: "Ovozni o'chirish",
        Feature.EXTRACT_AUDIO: "Ovozni ajratish (MP3)",
        Feature.GIF: "GIF yaratish",
        Feature.CIRCULAR: "Doira profil video",
        Feature.REVERSE: "Orqaga aylantirish",
        Feature.RESIZE: "O'lchamni moslashtirish",
        Feature.THUMBNAIL: "Thumbnail olish",
        Feature.WATERMARK: "Watermark qo'shish",
        Feature.INFO: "Video haqida ma'lumot",
    },
    "ru": {
        Feature.VIDEO_NOTE: "Видео-заметка",
        Feature.COMPRESS: "Сжать",
        Feature.TRIM: "Обрезать",
        Feature.SPEED: "Изменить скорость",
        Feature.REMOVE_AUDIO: "Удалить звук",
        Feature.EXTRACT_AUDIO: "Извлечь звук (MP3)",
        Feature.GIF: "Создать GIF",
        Feature.CIRCULAR: "Круглое видео профиля",
        Feature.REVERSE: "Реверс видео",
        Feature.RESIZE: "Изменить формат",
        Feature.THUMBNAIL: "Превью",
        Feature.WATERMARK: "Добавить водяной знак",
        Feature.INFO: "Информация о видео",
    },
    "en": {
        Feature.VIDEO_NOTE: "Make Video Note",
        Feature.COMPRESS: "Compress",
        Feature.TRIM: "Trim",
        Feature.SPEED: "Change speed",
        Feature.REMOVE_AUDIO: "Remove audio",
        Feature.EXTRACT_AUDIO: "Extract audio (MP3)",
        Feature.GIF: "Create GIF",
        Feature.CIRCULAR: "Circular profile video",
        Feature.REVERSE: "Reverse video",
        Feature.RESIZE: "Resize for platform",
        Feature.THUMBNAIL: "Generate thumbnail",
        Feature.WATERMARK: "Add watermark",
        Feature.INFO: "Video info",
    },
}


def features_keyboard(lang: str, enabled_features: dict, job_token: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    labels = FEATURE_LABELS.get(lang, FEATURE_LABELS["en"])
    for feature in Feature:
        if not enabled_features.get(feature.value, True):
            continue
        emoji = FEATURE_EMOJI[feature]
        label = labels[feature]
        b.button(text=f"{emoji} {label}", callback_data=f"feat:{feature.value}:{job_token}")
    b.adjust(2)
    return b.as_markup()


def quality_keyboard(job_token: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Standard", callback_data=f"quality:standard:{job_token}")
    b.button(text="HD", callback_data=f"quality:hd:{job_token}")
    b.button(text="Ultra", callback_data=f"quality:ultra:{job_token}")
    b.adjust(3)
    return b.as_markup()


def speed_keyboard(job_token: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in SPEED_OPTIONS:
        b.button(text=f"{s}x", callback_data=f"speed:{s}:{job_token}")
    b.adjust(len(SPEED_OPTIONS))
    return b.as_markup()


def resize_keyboard(job_token: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    names = {
        "reels": "📸 Instagram Reels", "tiktok": "🎵 TikTok",
        "shorts": "▶️ YouTube Shorts", "telegram": "✈️ Telegram", "square": "⬛️ Square",
    }
    for key in RESIZE_FORMATS:
        b.button(text=names.get(key, key), callback_data=f"resize:{key}:{job_token}")
    b.adjust(2)
    return b.as_markup()


def watermark_type_keyboard(job_token: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔤 Text", callback_data=f"wm:text:{job_token}")
    b.button(text="🖼 Logo", callback_data=f"wm:logo:{job_token}")
    b.adjust(2)
    return b.as_markup()


def compress_level_keyboard(job_token: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Light", callback_data=f"complevel:light:{job_token}")
    b.button(text="Medium", callback_data=f"complevel:medium:{job_token}")
    b.button(text="Strong", callback_data=f"complevel:strong:{job_token}")
    b.adjust(3)
    return b.as_markup()


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    labels = {
        "uz": ["👤 Profil", "🔗 Referal", "🏆 Reyting", "🌐 Til"],
        "ru": ["👤 Профиль", "🔗 Реферал", "🏆 Рейтинг", "🌐 Язык"],
        "en": ["👤 Profile", "🔗 Referral", "🏆 Leaderboard", "🌐 Language"],
    }[lang if lang in ("uz", "ru", "en") else "en"]
    b.button(text=labels[0], callback_data="menu:profile")
    b.button(text=labels[1], callback_data="menu:referral")
    b.button(text=labels[2], callback_data="menu:leaderboard")
    b.button(text=labels[3], callback_data="menu:language")
    b.adjust(2)
    return b.as_markup()
