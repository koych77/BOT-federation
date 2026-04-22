from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import MemberApplication, Payment
from app.services.labels import APPLICATION_TYPE_LABELS, AUTO_CHECK_LABELS, FEE_LABELS, ROLE_LABELS, label
from app.services.storage import read_receipt_bytes

router = Router()
FORM_PATH = Path(__file__).resolve().parent.parent / "assets" / "forms" / "zayavlenie-na-vstuplenie-v-bfb.doc"


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
    text = "Здравствуйте! Здесь можно подать анкету в БФБ и загрузить подтверждение оплаты."
    if settings.webapp_url.startswith("https://"):
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
        await message.answer(text, reply_markup=keyboard)
        return

    await message.answer(f"{text}\n\nЛокальная форма для теста: {settings.webapp_url}")


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


@router.message(Command("id"))
async def show_id(message: Message) -> None:
    if not message.from_user:
        await message.answer("Не удалось определить Telegram ID.")
        return
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(Command("form"))
async def send_application_form(message: Message) -> None:
    await send_application_form_document(message)


async def send_application_form_document(message: Message) -> None:
    if not FORM_PATH.exists():
        await message.answer("Бланк заявления пока не найден на сервере.")
        return
    await message.answer_document(
        FSInputFile(FORM_PATH, filename="zayavlenie-na-vstuplenie-v-bfb.doc"),
        caption="Бланк заявления на вступление в БФБ. Его можно скачать, заполнить и передать администратору.",
    )


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

    import json

    try:
        note_items = json.loads(payment.auto_check_notes or "[]")
    except json.JSONDecodeError:
        note_items = [payment.auto_check_notes]
    notes = "\n".join(f"- {item}" for item in note_items[:8])
    auto_label = label(AUTO_CHECK_LABELS, payment.auto_check_status)
    decision_line = (
        "Решение бота: можно проверять быстро, формальные признаки совпали."
        if payment.auto_check_status == "ready_for_admin_approval"
        else "Решение бота: нужна ручная проверка администратором."
    )
    text = (
        f"Новая заявка #{application.id}\n"
        f"\nУчастник\n"
        f"ФИО: {application.full_name}\n"
        f"Телефон: {application.phone}\n"
        f"Город: {application.city}\n"
        f"Клуб: {application.club or '-'}\n"
        f"Роль: {label(ROLE_LABELS, application.role)}\n"
        f"\nЗаявление и оплата\n"
        f"Тип заявки: {label(APPLICATION_TYPE_LABELS, application.application_type)}\n"
        f"Назначение оплаты: {label(FEE_LABELS, payment.fee_type)}\n"
        f"Год членства: {application.membership_year}\n"
        f"Сумма: {payment.paid_amount} / ожидается {payment.expected_amount} BYN\n"
        f"Дата оплаты: {payment.payment_date or '-'}\n"
        f"Плательщик: {payment.payer_full_name}\n"
        f"Операция: {payment.operation_id or '-'}\n"
        f"\nАвтопроверка\n"
        f"Статус: {auto_label}\n"
        f"{decision_line}\n"
        f"{notes}"
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
