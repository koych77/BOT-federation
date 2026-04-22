import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def expected_amount_for(fee_type: str, entry_fee: float, membership_fee: float) -> Decimal:
    if fee_type == "entry":
        return Decimal(str(entry_fee))
    if fee_type == "membership":
        return Decimal(str(membership_fee))
    if fee_type == "both":
        return Decimal(str(entry_fee + membership_fee))
    raise ValueError("Unknown fee type")


def run_preliminary_checks(
    db: Session,
    *,
    fee_type: str,
    expected_amount: Decimal,
    paid_amount: Decimal | None,
    payment_date: date | None,
    payer_full_name: str,
    member_full_name: str,
    operation_id: str | None,
    receipt_sha256: str,
    receipt_size: int,
    content_type: str,
    original_name: str,
    max_upload_bytes: int,
) -> tuple[str, str]:
    notes: list[str] = []
    status = "passed"

    if content_type not in ALLOWED_CONTENT_TYPES:
        status = "flagged"
        notes.append("Файл должен быть PDF, JPG, PNG или WEBP.")

    if receipt_size <= 0:
        status = "flagged"
        notes.append("Файл пустой.")

    if receipt_size > max_upload_bytes:
        status = "flagged"
        notes.append("Файл больше разрешенного лимита.")

    suffix = Path(original_name).suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        status = "flagged"
        notes.append("Расширение файла не похоже на чек.")

    if paid_amount is None:
        status = "flagged"
        notes.append("Не указана сумма оплаты.")
    elif paid_amount != expected_amount:
        status = "flagged"
        notes.append(f"Указанная сумма {paid_amount} не совпадает с ожидаемой {expected_amount}.")

    if not payment_date:
        status = "flagged"
        notes.append("Не указана дата оплаты.")
    elif payment_date > date.today():
        status = "flagged"
        notes.append("Дата оплаты находится в будущем.")
    elif payment_date < date.today() - timedelta(days=370):
        status = "flagged"
        notes.append("Дата оплаты старше одного года.")

    member_parts = {part.lower() for part in member_full_name.split() if len(part) >= 3}
    payer_parts = {part.lower() for part in payer_full_name.split() if len(part) >= 3}
    if member_parts and payer_parts and not (member_parts & payer_parts):
        status = "flagged"
        notes.append("ФИО плательщика не похоже на ФИО участника.")

    if operation_id:
        duplicate_operation = db.scalar(select(Payment).where(Payment.operation_id == operation_id))
        if duplicate_operation:
            status = "flagged"
            notes.append("Номер операции уже встречался в другой заявке.")

    duplicate_file = db.scalar(select(Payment).where(Payment.receipt_sha256 == receipt_sha256))
    if duplicate_file:
        status = "flagged"
        notes.append("Такой же файл чека уже загружался.")

    if fee_type not in {"entry", "membership", "both"}:
        status = "flagged"
        notes.append("Неизвестный тип взноса.")

    if not notes:
        notes.append("Первичная проверка пройдена. Требуется финальное подтверждение администратором.")

    return status, json.dumps(notes, ensure_ascii=False)
