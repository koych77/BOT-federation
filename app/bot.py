from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import MemberApplication, Payment
from app.services.storage import read_receipt_bytes

router = Router()


def _is_admin(user_id: int | None, settings: Settings) -> bool:
    return bool(user_id and user_id in settings.admin_telegram_ids)


def admin_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить", callback_data=f"approve:{payment_id}"),
                InlineKeyboardButton(text="Новый чек", callback_data=f"need_receipt:{payment_id}"),
            ],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{payment_id}")],
        ]
    )


@router.message(Command("start"))
async def start(message: Message) -> None:
    settings = get_settings()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть анкету",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )
    await message.answer(
        "Здравствуйте! Здесь можно подать анкету в БФБ и загрузить подтверждение оплаты.",
        reply_markup=keyboard,
    )


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    settings = get_settings()
    if not _is_admin(message.from_user.id if message.from_user else None, settings):
        await message.answer("Эта команда доступна только администраторам.")
        return

    export_url = f"{settings.webapp_url.rstrip('/')}/admin/export.xlsx"
    if settings.admin_export_token:
        export_url += f"?token={settings.admin_export_token}"
    await message.answer(f"Админ-панель MVP: выгрузка Excel\n{export_url}")


@router.callback_query(F.data.startswith("approve:"))
async def approve_payment(callback: CallbackQuery) -> None:
    await _set_payment_status(callback, "approved", "Оплата подтверждена.")


@router.callback_query(F.data.startswith("reject:"))
async def reject_payment(callback: CallbackQuery) -> None:
    await _set_payment_status(callback, "rejected", "Оплата отклонена.")


@router.callback_query(F.data.startswith("need_receipt:"))
async def need_receipt(callback: CallbackQuery) -> None:
    await _set_payment_status(callback, "needs_new_receipt", "Нужно загрузить новый чек.")


async def _set_payment_status(callback: CallbackQuery, status: str, user_text: str) -> None:
    settings = get_settings()
    if not _is_admin(callback.from_user.id if callback.from_user else None, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, raw_id = (callback.data or "").split(":", 1)
    with SessionLocal() as db:
        payment = db.get(Payment, int(raw_id))
        if not payment:
            await callback.answer("Оплата не найдена", show_alert=True)
            return
        payment.admin_status = status
        payment.reviewed_by_telegram_id = callback.from_user.id
        payment.reviewed_at = datetime.now(timezone.utc)
        payment.application.status = "confirmed" if status == "approved" else status
        db.commit()
        telegram_id = payment.application.telegram_id

    await callback.answer("Готово")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"{user_text} Заявка #{payment.application_id}.")

    if telegram_id and settings.bot_token:
        bot = Bot(settings.bot_token)
        try:
            await bot.send_message(telegram_id, f"{user_text} Заявка #{payment.application_id}.")
        finally:
            await bot.session.close()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def notify_admins(application: MemberApplication, payment: Payment, db: Session) -> None:
    settings = get_settings()
    if not settings.bot_token or not settings.admin_telegram_ids:
        return

    notes = payment.auto_check_notes.replace("[", "").replace("]", "").replace('"', "")
    text = (
        f"Новая заявка #{application.id}\n"
        f"ФИО: {application.full_name}\n"
        f"Город: {application.city}\n"
        f"Клуб: {application.club or '-'}\n"
        f"Тип взноса: {payment.fee_type}\n"
        f"Сумма: {payment.paid_amount} / ожидается {payment.expected_amount}\n"
        f"Автопроверка: {payment.auto_check_status}\n"
        f"Заметки: {notes}"
    )

    bot = Bot(settings.bot_token)
    try:
        for admin_id in settings.admin_telegram_ids:
            await bot.send_message(admin_id, text, reply_markup=admin_keyboard(payment.id))
            try:
                if payment.receipt_path.startswith("s3://"):
                    document = BufferedInputFile(
                        read_receipt_bytes(settings, payment.receipt_path),
                        filename=payment.receipt_original_name,
                    )
                else:
                    document = FSInputFile(payment.receipt_path, filename=payment.receipt_original_name)
                await bot.send_document(admin_id, document, caption=f"Чек по заявке #{application.id}")
            except Exception:
                await bot.send_message(admin_id, f"Чек по заявке #{application.id} не удалось приложить автоматически.")
    finally:
        await bot.session.close()
