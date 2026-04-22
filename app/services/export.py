from io import BytesIO
import json

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import MemberApplication, Payment


def _header(ws, labels: list[str]) -> None:
    ws.append(labels)
    fill = PatternFill("solid", fgColor="111111")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill


def _autosize(ws) -> None:
    for column in ws.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(width + 2, 12), 48)


def build_members_export(db: Session) -> bytes:
    rows = db.scalars(
        select(MemberApplication)
        .options(joinedload(MemberApplication.payment))
        .order_by(MemberApplication.created_at.desc())
    ).all()

    wb = Workbook()
    ws_members = wb.active
    ws_members.title = "Участники"
    _header(
        ws_members,
        [
            "ID",
            "ФИО",
            "Telegram ID",
            "Username",
            "Телефон",
            "Email",
            "Город",
            "Клуб",
            "Тренер",
            "Роль",
            "Тип заявки",
            "Год",
            "Статус заявки",
            "Создано",
        ],
    )

    ws_payments = wb.create_sheet("Оплаты")
    _header(
        ws_payments,
        [
            "ID заявки",
            "ФИО",
            "Тип взноса",
            "Ожидаемая сумма",
            "Указанная сумма",
            "Дата оплаты",
            "Плательщик",
            "Номер операции",
            "Канал оплаты",
            "Автопроверка",
            "Статус админа",
            "Комментарий",
            "Кто проверил",
            "Когда проверил",
        ],
    )

    ws_checks = wb.create_sheet("Проверки")
    _header(ws_checks, ["ID заявки", "ФИО", "Файл", "SHA256", "Размер", "MIME", "Заметки проверки"])

    for app in rows:
        payment: Payment | None = app.payment
        ws_members.append(
            [
                app.id,
                app.full_name,
                app.telegram_id,
                app.telegram_username,
                app.phone,
                app.email,
                app.city,
                app.club,
                app.coach,
                app.role,
                app.application_type,
                app.membership_year,
                app.status,
                app.created_at.isoformat() if app.created_at else "",
            ]
        )

        if payment:
            ws_payments.append(
                [
                    app.id,
                    app.full_name,
                    payment.fee_type,
                    float(payment.expected_amount),
                    float(payment.paid_amount) if payment.paid_amount is not None else "",
                    payment.payment_date.isoformat() if payment.payment_date else "",
                    payment.payer_full_name,
                    payment.operation_id,
                    payment.payment_channel,
                    payment.auto_check_status,
                    payment.admin_status,
                    payment.admin_comment,
                    payment.reviewed_by_telegram_id,
                    payment.reviewed_at.isoformat() if payment.reviewed_at else "",
                ]
            )
            try:
                notes = "; ".join(json.loads(payment.auto_check_notes or "[]"))
            except json.JSONDecodeError:
                notes = payment.auto_check_notes
            ws_checks.append(
                [
                    app.id,
                    app.full_name,
                    payment.receipt_original_name,
                    payment.receipt_sha256,
                    payment.receipt_size,
                    payment.receipt_content_type,
                    notes,
                ]
            )

    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        _autosize(ws)

    output = BytesIO()
    wb.save(output)
    return output.getvalue()
