from enum import Enum


class Feature(str, Enum):
    VIDEO_NOTE = "video_note"
    COMPRESS = "compress"
    TRIM = "trim"
    SPEED = "speed"
    REMOVE_AUDIO = "remove_audio"
    EXTRACT_AUDIO = "extract_audio"
    GIF = "gif"
    CIRCULAR = "circular"
    REVERSE = "reverse"
    RESIZE = "resize"
    THUMBNAIL = "thumbnail"
    WATERMARK = "watermark"
    INFO = "info"


FEATURE_EMOJI = {
    Feature.VIDEO_NOTE: "🎥",
    Feature.COMPRESS: "🗜",
    Feature.TRIM: "✂️",
    Feature.SPEED: "⚡️",
    Feature.REMOVE_AUDIO: "🔇",
    Feature.EXTRACT_AUDIO: "🎵",
    Feature.GIF: "🎞",
    Feature.CIRCULAR: "⭕️",
    Feature.REVERSE: "⏪",
    Feature.RESIZE: "📐",
    Feature.THUMBNAIL: "🖼",
    Feature.WATERMARK: "💧",
    Feature.INFO: "ℹ️",
}

# Video note quality presets: (side_px, crf, bitrate_hint)
VIDEO_NOTE_QUALITY = {
    "standard": {"size": 360, "crf": 28},
    "hd": {"size": 480, "crf": 24},
    "ultra": {"size": 640, "crf": 20},
}

SPEED_OPTIONS = ["0.5", "1.0", "1.5", "2.0", "3.0"]

RESIZE_FORMATS = {
    "reels": (1080, 1920),
    "tiktok": (1080, 1920),
    "shorts": (1080, 1920),
    "telegram": (1280, 720),
    "square": (1080, 1080),
}

COMPRESS_LEVELS = {
    "light": 26,
    "medium": 30,
    "strong": 34,
}

# Simple in-code feature toggle defaults (overridable from admin panel -> DB Settings table)
DEFAULT_ENABLED_FEATURES = {f.value: True for f in Feature}
