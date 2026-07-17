from __future__ import annotations

from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile

from config.constants import Feature
from database import crud
from database.db import get_session
from handlers.states import TrimStates, WatermarkStates
from keyboards.inline import (
    features_keyboard, quality_keyboard, speed_keyboard, resize_keyboard,
    watermark_type_keyboard, compress_level_keyboard, main_menu_keyboard,
)
from services import ffmpeg_service as ff
from services.job_store import job_store, JobContext
from services.queue_service import video_queue
from utils.filesystem import safe_name, user_temp_dir, cleanup_path, human_size, human_duration, parse_timecode
from utils.i18n import t
from utils.progress import ProgressMessage

router = Router(name="video")


# ---------------------------------------------------------------------
# Upload entrypoint
# ---------------------------------------------------------------------

@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def handle_video_upload(message: Message, session, db_user, bot: Bot):
    lang = db_user.language

    if db_user.is_banned:
        return

    maintenance = (await crud.get_setting(session, "maintenance_mode", "0")) == "1"
    if maintenance and db_user.id not in _admin_ids():
        await message.answer(t(lang, "maintenance"))
        return

    tg_file = message.video or message.document
    file_size = tg_file.file_size or 0

    max_mb = int(await crud.get_setting(
        session,
        "max_upload_mb_premium" if db_user.is_premium else "max_upload_mb",
    ))
    if file_size > max_mb * 1024 * 1024:
        await message.answer(t(lang, "error_too_large", limit=max_mb))
        return

    duration = getattr(tg_file, "duration", None) or 0
    max_dur = int(await crud.get_setting(session, "max_duration_sec"))
    if duration and duration > max_dur and not db_user.is_premium:
        await message.answer(t(lang, "error_too_long", limit=max_dur))
        return

    status_msg = await message.answer(t(lang, "downloading"))

    dest_dir = user_temp_dir(db_user.id)
    dest_path = dest_dir / safe_name("input", "mp4")
    try:
        file = await bot.get_file(tg_file.file_id)
        await bot.download_file(file.file_path, destination=dest_path)
    except Exception:
        await status_msg.edit_text(t(lang, "error_generic"))
        return

    ctx = job_store.create(
        user_id=db_user.id, chat_id=message.chat.id,
        input_path=dest_path, file_size=file_size, is_premium=db_user.is_premium,
    )

    enabled = await crud.get_enabled_features(session)
    await status_msg.edit_text(t(lang, "video_received"))
    await message.answer(
        t(lang, "video_received"),
        reply_markup=features_keyboard(lang, enabled, ctx.token),
    )


def _admin_ids() -> set[int]:
    from config.settings import settings
    return settings.admin_ids


# ---------------------------------------------------------------------
# Feature selection
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("feat:"))
async def cb_feature_selected(callback: CallbackQuery, db_user, state: FSMContext):
    _, feature, token = callback.data.split(":")
    ctx = job_store.get(token)
    lang = db_user.language
    if not ctx:
        await callback.answer(t(lang, "error_generic"), show_alert=True)
        return

    if feature == Feature.VIDEO_NOTE.value:
        await callback.message.edit_text(t(lang, "choose_quality"), reply_markup=quality_keyboard(token))

    elif feature == Feature.COMPRESS.value:
        await callback.message.edit_text(t(lang, "choose_quality"), reply_markup=compress_level_keyboard(token))

    elif feature == Feature.SPEED.value:
        await callback.message.edit_text(t(lang, "choose_speed"), reply_markup=speed_keyboard(token))

    elif feature == Feature.RESIZE.value:
        await callback.message.edit_text(t(lang, "choose_resize"), reply_markup=resize_keyboard(token))

    elif feature == Feature.WATERMARK.value:
        await callback.message.edit_text("💧", reply_markup=watermark_type_keyboard(token))

    elif feature == Feature.TRIM.value:
        await state.update_data(job_token=token)
        await state.set_state(TrimStates.waiting_start)
        await callback.message.edit_text(t(lang, "ask_trim_start"))

    elif feature in (
        Feature.REMOVE_AUDIO.value, Feature.EXTRACT_AUDIO.value, Feature.GIF.value,
        Feature.CIRCULAR.value, Feature.REVERSE.value, Feature.THUMBNAIL.value, Feature.INFO.value,
    ):
        await _enqueue(callback, ctx, feature, {})

    await callback.answer()


@router.callback_query(F.data.startswith("quality:"))
async def cb_quality(callback: CallbackQuery, db_user):
    _, quality, token = callback.data.split(":")
    ctx = job_store.get(token)
    if not ctx:
        await callback.answer()
        return
    await _enqueue(callback, ctx, Feature.VIDEO_NOTE.value, {"quality": quality})


@router.callback_query(F.data.startswith("complevel:"))
async def cb_complevel(callback: CallbackQuery, db_user):
    _, level, token = callback.data.split(":")
    ctx = job_store.get(token)
    if not ctx:
        await callback.answer()
        return
    await _enqueue(callback, ctx, Feature.COMPRESS.value, {"level": level})


@router.callback_query(F.data.startswith("speed:"))
async def cb_speed(callback: CallbackQuery, db_user):
    _, speed, token = callback.data.split(":")
    ctx = job_store.get(token)
    if not ctx:
        await callback.answer()
        return
    await _enqueue(callback, ctx, Feature.SPEED.value, {"speed": float(speed)})


@router.callback_query(F.data.startswith("resize:"))
async def cb_resize(callback: CallbackQuery, db_user):
    _, fmt, token = callback.data.split(":")
    ctx = job_store.get(token)
    if not ctx:
        await callback.answer()
        return
    await _enqueue(callback, ctx, Feature.RESIZE.value, {"format": fmt})


@router.callback_query(F.data.startswith("wm:"))
async def cb_watermark_type(callback: CallbackQuery, db_user, state: FSMContext):
    _, kind, token = callback.data.split(":")
    ctx = job_store.get(token)
    lang = db_user.language
    if not ctx:
        await callback.answer()
        return
    await state.update_data(job_token=token, wm_kind=kind)
    if kind == "text":
        await state.set_state(WatermarkStates.waiting_text)
        await callback.message.edit_text(t(lang, "ask_watermark_text"))
    else:
        await state.set_state(WatermarkStates.waiting_logo)
        await callback.message.edit_text(t(lang, "ask_watermark_logo"))
    await callback.answer()


# ---------------------------------------------------------------------
# FSM text inputs: trim start/end, watermark text
# ---------------------------------------------------------------------

@router.message(TrimStates.waiting_start)
async def trim_start_input(message: Message, state: FSMContext, db_user):
    lang = db_user.language
    tc = parse_timecode(message.text or "")
    if not tc:
        await message.answer(t(lang, "invalid_time"))
        return
    await state.update_data(trim_start=tc)
    await state.set_state(TrimStates.waiting_end)
    await message.answer(t(lang, "ask_trim_end"))


@router.message(TrimStates.waiting_end)
async def trim_end_input(message: Message, state: FSMContext, db_user):
    lang = db_user.language
    tc = parse_timecode(message.text or "")
    if not tc:
        await message.answer(t(lang, "invalid_time"))
        return
    data = await state.get_data()
    token = data["job_token"]
    ctx = job_store.get(token)
    await state.clear()
    if not ctx:
        await message.answer(t(lang, "error_generic"))
        return
    await _enqueue_from_message(message, ctx, Feature.TRIM.value,
                                 {"start": data["trim_start"], "end": tc})


@router.message(WatermarkStates.waiting_text)
async def watermark_text_input(message: Message, state: FSMContext, db_user):
    lang = db_user.language
    data = await state.get_data()
    token = data["job_token"]
    ctx = job_store.get(token)
    await state.clear()
    if not ctx:
        await message.answer(t(lang, "error_generic"))
        return
    await _enqueue_from_message(message, ctx, Feature.WATERMARK.value,
                                 {"kind": "text", "text": message.text or ""})


@router.message(WatermarkStates.waiting_logo, F.photo | F.document)
async def watermark_logo_input(message: Message, state: FSMContext, db_user, bot: Bot):
    lang = db_user.language
    data = await state.get_data()
    token = data["job_token"]
    ctx = job_store.get(token)
    await state.clear()
    if not ctx:
        await message.answer(t(lang, "error_generic"))
        return

    logo_file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    logo_path = user_temp_dir(db_user.id) / safe_name("logo", "png")
    file = await bot.get_file(logo_file_id)
    await bot.download_file(file.file_path, destination=logo_path)

    await _enqueue_from_message(message, ctx, Feature.WATERMARK.value,
                                 {"kind": "logo", "logo_path": str(logo_path)})


# ---------------------------------------------------------------------
# Enqueue + processing
# ---------------------------------------------------------------------

async def _enqueue(callback: CallbackQuery, ctx: JobContext, feature: str, params: dict) -> None:
    lang_row = None
    status_msg = await callback.message.edit_text("⏳")
    await _submit(callback.bot, ctx, feature, params, status_msg.chat.id, status_msg.message_id)
    await callback.answer()


async def _enqueue_from_message(message: Message, ctx: JobContext, feature: str, params: dict) -> None:
    status_msg = await message.answer("⏳")
    await _submit(message.bot, ctx, feature, params, status_msg.chat.id, status_msg.message_id)


async def _submit(bot: Bot, ctx: JobContext, feature: str, params: dict, chat_id: int, message_id: int) -> None:
    async with get_session() as session:
        user = await crud.get_user(session, ctx.user_id)
        lang = user.language if user else "uz"

        # premium-only features gate (all features free by default; extend as needed)
        pos = video_queue.size() + 1
        progress = ProgressMessage(bot, chat_id, message_id, lang)
        if pos > 1:
            await progress.update("process", t(lang, "queue_position", position=pos))

    async def job():
        await _process(bot, ctx, feature, params, chat_id, message_id)

    await video_queue.submit(ctx.user_id, feature, job, is_premium=ctx.is_premium)


async def _process(bot: Bot, ctx: JobContext, feature: str, params: dict,
                    chat_id: int, message_id: int) -> None:
    async with get_session() as session:
        user = await crud.get_user(session, ctx.user_id)
        lang = user.language if user else "uz"
        progress = ProgressMessage(bot, chat_id, message_id, lang)

        input_path: Path = ctx.input_path
        out_dir = input_path.parent
        output_path: Path | None = None
        result = "ok"
        error_text = None

        try:
            await progress.update("process")

            if feature == Feature.INFO.value:
                info = await ff.get_video_info(input_path)
                text = t(lang, "video_info",
                         duration=human_duration(info["duration"]),
                         width=info["width"], height=info["height"], fps=info["fps"],
                         vcodec=info["video_codec"], acodec=info["audio_codec"],
                         size=human_size(info["size_bytes"] or ctx.file_size))
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
                await crud.add_log(session, ctx.user_id, feature, user.username if user else None, ctx.file_size, "ok")
                await session.commit()
                return

            elif feature == Feature.VIDEO_NOTE.value:
                output_path = out_dir / safe_name("note", "mp4")
                await ff.to_video_note(input_path, output_path, params.get("quality", "hd"))
                await progress.update("upload")
                await bot.send_video_note(chat_id, FSInputFile(output_path))

            elif feature == Feature.COMPRESS.value:
                output_path = out_dir / safe_name("compressed", "mp4")
                await ff.compress_video(input_path, output_path, params.get("level", "medium"))
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))

            elif feature == Feature.TRIM.value:
                output_path = out_dir / safe_name("trimmed", "mp4")
                await ff.trim_video(input_path, output_path, params["start"], params["end"])
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))

            elif feature == Feature.SPEED.value:
                output_path = out_dir / safe_name("speed", "mp4")
                await ff.change_speed(input_path, output_path, float(params.get("speed", 1.0)))
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))

            elif feature == Feature.REMOVE_AUDIO.value:
                output_path = out_dir / safe_name("noaudio", "mp4")
                await ff.remove_audio(input_path, output_path)
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))

            elif feature == Feature.EXTRACT_AUDIO.value:
                output_path = out_dir / safe_name("audio", "mp3")
                await ff.extract_audio(input_path, output_path)
                await progress.update("upload")
                await bot.send_audio(chat_id, FSInputFile(output_path))

            elif feature == Feature.GIF.value:
                output_path = out_dir / safe_name("clip", "gif")
                await ff.make_gif(input_path, output_path)
                await progress.update("upload")
                await bot.send_animation(chat_id, FSInputFile(output_path))

            elif feature == Feature.CIRCULAR.value:
                output_path = out_dir / safe_name("circular", "mp4")
                await ff.to_circular(input_path, output_path)
                await progress.update("upload")
                await bot.send_video_note(chat_id, FSInputFile(output_path))

            elif feature == Feature.REVERSE.value:
                output_path = out_dir / safe_name("reversed", "mp4")
                await ff.reverse_video(input_path, output_path)
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))

            elif feature == Feature.RESIZE.value:
                output_path = out_dir / safe_name("resized", "mp4")
                await ff.resize_video(input_path, output_path, params.get("format", "telegram"))
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))

            elif feature == Feature.THUMBNAIL.value:
                output_path = out_dir / safe_name("thumb", "jpg")
                await ff.generate_thumbnail(input_path, output_path)
                await progress.update("upload")
                await bot.send_photo(chat_id, FSInputFile(output_path))

            elif feature == Feature.WATERMARK.value:
                output_path = out_dir / safe_name("watermarked", "mp4")
                if params.get("kind") == "text":
                    await ff.add_text_watermark(input_path, output_path, params.get("text", ""))
                else:
                    await ff.add_logo_watermark(input_path, Path(params["logo_path"]), output_path)
                await progress.update("upload")
                await bot.send_video(chat_id, FSInputFile(output_path))
                if params.get("kind") == "logo":
                    cleanup_path(Path(params["logo_path"]))

            await progress.update("done")
            await crud.increment_conversions(session, ctx.user_id)

        except Exception as e:  # noqa: BLE001
            result = "error"
            error_text = str(e)[:500]
            await progress.error(t(lang, "error_generic"))

        finally:
            await crud.add_log(session, ctx.user_id, feature, user.username if user else None,
                                ctx.file_size, result, error_text)
            await session.commit()
            cleanup_path(input_path)
            if output_path:
                cleanup_path(output_path)
            job_store.drop(ctx.token)
