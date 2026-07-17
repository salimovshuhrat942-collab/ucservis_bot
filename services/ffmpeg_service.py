"""
All FFmpeg-based video operations live here. Every function is async
(uses asyncio.create_subprocess_exec) so the bot event loop is never blocked.
Every function returns the output file Path on success and raises
FFmpegError on failure.
"""
from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path

from config.settings import settings


class FFmpegError(RuntimeError):
    pass


async def _run(cmd: list[str], timeout: int = 600) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise FFmpegError("FFmpeg timed out")

    if proc.returncode != 0:
        raise FFmpegError(stderr.decode(errors="ignore")[-2000:])


def _preset() -> str:
    return settings.FFMPEG_PRESET


def _threads() -> list[str]:
    return ["-threads", str(settings.FFMPEG_THREADS)]


# ---------------------------------------------------------------------
# Probe / info
# ---------------------------------------------------------------------

async def probe(input_path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(input_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise FFmpegError(err.decode(errors="ignore"))
    return json.loads(out.decode())


async def get_video_info(input_path: Path) -> dict:
    data = await probe(input_path)
    v_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})

    duration = float(fmt.get("duration", 0) or 0)
    width = int(v_stream.get("width", 0) or 0)
    height = int(v_stream.get("height", 0) or 0)

    fps_raw = v_stream.get("r_frame_rate", "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = round(float(num) / float(den), 2) if float(den) else 0
    except Exception:
        fps = 0

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "video_codec": v_stream.get("codec_name", "n/a"),
        "audio_codec": a_stream.get("codec_name", "none"),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "has_audio": bool(a_stream),
    }


# ---------------------------------------------------------------------
# 1. Video -> Telegram Video Note (square, cropped center, <= 640px)
# ---------------------------------------------------------------------

async def to_video_note(input_path: Path, output_path: Path, quality: str = "hd") -> Path:
    from config.constants import VIDEO_NOTE_QUALITY
    q = VIDEO_NOTE_QUALITY.get(quality, VIDEO_NOTE_QUALITY["hd"])
    size = q["size"]
    crf = q["crf"]

    vf = (
        f"crop='min(iw,ih)':'min(iw,ih)',"
        f"scale={size}:{size}"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        *_threads(),
        "-vf", vf,
        "-c:v", "libx264", "-preset", _preset(), "-crf", str(crf),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-t", "60",  # telegram video notes max 60s
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 2. Compressor
# ---------------------------------------------------------------------

async def compress_video(input_path: Path, output_path: Path, level: str = "medium") -> Path:
    from config.constants import COMPRESS_LEVELS
    crf = COMPRESS_LEVELS.get(level, 30)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        *_threads(),
        "-c:v", "libx264", "-preset", _preset(), "-crf", str(crf),
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 3. Trimmer
# ---------------------------------------------------------------------

async def trim_video(input_path: Path, output_path: Path, start: str, end: str) -> Path:
    cmd = [
        "ffmpeg", "-y", "-ss", start, "-to", end, "-i", str(input_path),
        *_threads(),
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        "-c:a", "aac",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 4. Speed change (video + audio pitch-preserving via atempo chain)
# ---------------------------------------------------------------------

def _atempo_chain(speed: float) -> str:
    # atempo filter only supports 0.5-2.0 per instance -> chain for >2 or <0.5
    filters = []
    remaining = speed
    if remaining < 0.5:
        filters.append("atempo=0.5")
        remaining = remaining / 0.5
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.3f}")
    return ",".join(filters)


async def change_speed(input_path: Path, output_path: Path, speed: float) -> Path:
    vf = f"setpts={1/speed:.5f}*PTS"
    af = _atempo_chain(speed)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        *_threads(),
        "-vf", vf, "-af", af,
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        "-c:a", "aac",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 5. Remove audio
# ---------------------------------------------------------------------

async def remove_audio(input_path: Path, output_path: Path) -> Path:
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-c:v", "copy", "-an", str(output_path)]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 6. Extract audio (MP3)
# ---------------------------------------------------------------------

async def extract_audio(input_path: Path, output_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 7. GIF creator
# ---------------------------------------------------------------------

async def make_gif(input_path: Path, output_path: Path, start: str = "0", duration: int = 5, fps: int = 12, width: int = 480) -> Path:
    palette = output_path.with_suffix(".png")
    vf_palette = f"fps={fps},scale={width}:-1:flags=lanczos,palettegen"
    cmd1 = [
        "ffmpeg", "-y", "-ss", start, "-t", str(duration), "-i", str(input_path),
        "-vf", vf_palette, str(palette),
    ]
    await _run(cmd1)

    vf_gif = f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse"
    cmd2 = [
        "ffmpeg", "-y", "-ss", start, "-t", str(duration), "-i", str(input_path),
        "-i", str(palette),
        "-lavfi", vf_gif,
        str(output_path),
    ]
    await _run(cmd2)
    palette.unlink(missing_ok=True)
    return output_path


# ---------------------------------------------------------------------
# 8. Circular profile video (round mask, webm with alpha for TG profile video)
# ---------------------------------------------------------------------

async def to_circular(input_path: Path, output_path: Path, size: int = 400) -> Path:
    # Telegram renders profile videos / video notes inside a circular mask
    # client-side, so a clean square crop is all that's needed. (We tested
    # a VP9-with-alpha approach; this ffmpeg/libvpx build silently drops the
    # alpha plane on encode, which would ship a broken transparency instead
    # of a real one — a square MP4 is both correct and portable.)
    vf = f"crop='min(iw,ih)':'min(iw,ih)',scale={size}:{size}"
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        *_threads(),
        "-vf", vf,
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-t", "10",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 9. Reverse video
# ---------------------------------------------------------------------

async def reverse_video(input_path: Path, output_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", "reverse", "-af", "areverse",
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 10. Resize for platform
# ---------------------------------------------------------------------

async def resize_video(input_path: Path, output_path: Path, target_format: str) -> Path:
    from config.constants import RESIZE_FORMATS
    w, h = RESIZE_FORMATS.get(target_format, (1080, 1920))
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        *_threads(),
        "-vf", vf,
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        "-c:a", "aac",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 11. Thumbnail generator
# ---------------------------------------------------------------------

async def generate_thumbnail(input_path: Path, output_path: Path, timestamp: str = "00:00:01") -> Path:
    cmd = [
        "ffmpeg", "-y", "-ss", timestamp, "-i", str(input_path),
        "-frames:v", "1", "-q:v", "2",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


# ---------------------------------------------------------------------
# 12. Watermark (text or logo image)
# ---------------------------------------------------------------------

async def add_text_watermark(input_path: Path, output_path: Path, text: str,
                              position: str = "bottom_right") -> Path:
    positions = {
        "bottom_right": "x=w-tw-20:y=h-th-20",
        "bottom_left": "x=20:y=h-th-20",
        "top_right": "x=w-tw-20:y=20",
        "top_left": "x=20:y=20",
        "center": "x=(w-tw)/2:y=(h-th)/2",
    }
    pos = positions.get(position, positions["bottom_right"])
    safe_text = text.replace("'", r"\'").replace(":", r"\:")
    vf = (
        f"drawtext=text='{safe_text}':fontcolor=white@0.85:fontsize=28:"
        f"box=1:boxcolor=black@0.35:boxborderw=8:{pos}"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        *_threads(),
        "-vf", vf,
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ]
    await _run(cmd)
    return output_path


async def add_logo_watermark(input_path: Path, logo_path: Path, output_path: Path,
                              position: str = "bottom_right", scale_w: int = 120) -> Path:
    positions = {
        "bottom_right": "W-w-20:H-h-20",
        "bottom_left": "20:H-h-20",
        "top_right": "W-w-20:20",
        "top_left": "20:20",
        "center": "(W-w)/2:(H-h)/2",
    }
    overlay_pos = positions.get(position, positions["bottom_right"])
    filter_complex = f"[1:v]scale={scale_w}:-1[logo];[0:v][logo]overlay={overlay_pos}"
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path), "-i", str(logo_path),
        *_threads(),
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-preset", _preset(), "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ]
    await _run(cmd)
    return output_path
