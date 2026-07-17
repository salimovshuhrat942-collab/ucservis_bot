from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from config.settings import settings
from database import crud
from keyboards.inline import language_keyboard, main_menu_keyboard
from utils.i18n import t

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session, db_user, bot: Bot):
    # handle referral payload: /start ref_123456
    payload = command.args
    if payload and payload.startswith("ref_") and db_user.referred_by is None:
        try:
            referrer_id = int(payload.removeprefix("ref_"))
            if referrer_id != db_user.id:
                db_user.referred_by = referrer_id
                reward = int(await crud.get_setting(session, "referral_reward", "1"))
                await crud.apply_referral_reward(session, referrer_id, reward)
                try:
                    await bot.send_message(
                        referrer_id,
                        t((await crud.get_user(session, referrer_id)).language, "referral_text",
                          link="", reward=reward, count="").split("\n\n")[0]
                    )
                except Exception:
                    pass
        except ValueError:
            pass

    lang = db_user.language
    name = message.from_user.full_name
    await message.answer(t(lang, "welcome", name=name), reply_markup=main_menu_keyboard(lang))


@router.message(F.text == "/language")
async def cmd_language(message: Message, db_user):
    await message.answer(t(db_user.language, "choose_language"), reply_markup=language_keyboard())


@router.callback_query(F.data == "menu:language")
async def cb_language(callback: CallbackQuery, db_user):
    await callback.message.edit_text(t(db_user.language, "choose_language"), reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(callback: CallbackQuery, session, db_user):
    lang = callback.data.split(":")[1]
    await crud.set_language(session, db_user.id, lang)
    await callback.message.edit_text(t(lang, "language_set"))
    await callback.message.answer(
        t(lang, "welcome", name=callback.from_user.full_name),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery, db_user):
    lang = db_user.language
    premium_label = {"uz": "✅ Ha", "ru": "✅ Да", "en": "✅ Yes"}[lang] if db_user.is_premium else \
        {"uz": "❌ Yo'q", "ru": "❌ Нет", "en": "❌ No"}[lang]
    text = t(
        lang, "profile_text",
        id=db_user.id, lang=lang.upper(),
        date=db_user.registered_at.strftime("%Y-%m-%d"),
        conversions=db_user.conversions_count,
        referrals=db_user.referral_count,
        premium=premium_label,
    )
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "menu:referral")
async def cb_referral(callback: CallbackQuery, db_user, session):
    lang = db_user.language
    bot_username = settings.BOT_USERNAME or (await callback.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{db_user.id}"
    reward = await crud.get_setting(session, "referral_reward", "1")
    text = t(lang, "referral_text", link=link, reward=reward, count=db_user.referral_count)
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "menu:leaderboard")
async def cb_leaderboard(callback: CallbackQuery, db_user, session):
    lang = db_user.language
    top = await crud.top_referrers(session, limit=10)
    lines = [t(lang, "leaderboard") + "\n"]
    for i, u in enumerate(top, start=1):
        uname = f"@{u.username}" if u.username else str(u.id)
        lines.append(f"{i}. {uname} — {u.referral_count}")
    if not top:
        lines.append("—")
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, db_user):
    lang = db_user.language
    await callback.message.edit_text(
        t(lang, "welcome", name=callback.from_user.full_name),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery, db_user):
    # ForcedJoinMiddleware lets this callback through always; if we reach here,
    # re-running any handler chain would re-check on next action. Just confirm.
    lang = db_user.language
    await callback.message.edit_text(
        t(lang, "welcome", name=callback.from_user.full_name),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()
