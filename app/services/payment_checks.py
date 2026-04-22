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
    receipt_scan_status: str,
    receipt_scan_notes: list[str],
    receipt_text_has_amount: bool,
    receipt_text_has_operation: bool,
    receipt_text_has_name: bool,
) -> tuple[str, str]:
    notes: list[str] = []
    risk_count = 0
    manual_required = False

    if content_type not in ALLOWED_CONTENT_TYPES:
        risk_count += 1
        notes.append("Файл должен быть PDF, JPG, PNG или WEBP.")

    if receipt_size <= 0:
        risk_count += 1
        notes.append("Файл пустой.")

    if receipt_size > max_upload_bytes:
        risk_count += 1
        notes.append("Файл больше разрешенного лимита.")

    suffix = Path(original_name).suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        risk_count += 1
        notes.append("Расширение файла не похоже на чек.")

    if paid_amount is None:
        risk_count += 1
        notes.append("Не указана сумма оплаты.")
    elif paid_amount != expected_amount:
        risk_count += 1
        notes.append(f"Указанная сумма {paid_amount} не совпадает с ожидаемой {expected_amount}.")

    if not payment_date:
        risk_count += 1
        notes.append("Не указана дата оплаты.")
    elif payment_date > date.today():
        risk_count += 1
        notes.append("Дата оплаты находится в будущем.")
    elif payment_date < date.today() - timedelta(days=370):
        risk_count += 1
        notes.append("Дата оплаты старше одного года.")

    member_parts = {part.lower() for part in member_full_name.split() if len(part) >= 3}
    payer_parts = {part.lower() for part in payer_full_name.split() if len(part) >= 3}
    if member_parts and payer_parts and not (member_parts & payer_parts):
        risk_count += 1
        notes.append("ФИО плательщика не похоже на ФИО участника.")

    if operation_id:
        duplicate_operation = db.scalar(select(Payment).where(Payment.operation_id == operation_id))
        if duplicate_operation:
            risk_count += 1
            notes.append("Номер операции уже встречался в другой заявке.")

    duplicate_file = db.scalar(select(Payment).where(Payment.receipt_sha256 == receipt_sha256))
    if duplicate_file:
        risk_count += 1
        notes.append("Такой же файл чека уже загружался.")

    if fee_type not in {"entry", "membership", "both"}:
        risk_count += 1
        notes.append("Неизвестный тип взноса.")

    notes.extend(receipt_scan_notes)
    if receipt_scan_status in {"no_text", "image_needs_ocr", "unsupported"}:
        manual_required = True

    if receipt_scan_status == "text_extracted":
        if paid_amount is not None and receipt_text_has_amount:
            notes.append("В тексте чека найдена указанная сумма.")
        elif paid_amount is not None:
            risk_count += 1
            notes.append("В тексте чека не найдена указанная сумма.")

        if operation_id and receipt_text_has_operation:
            notes.append("В тексте чека найден номер операции.")
        elif operation_id:
            manual_required = True
            notes.append("Номер операции не найден в тексте чека.")

        if receipt_text_has_name:
            notes.append("В тексте чека найдено совпадение по ФИО.")
        else:
            manual_required = True
            notes.append("ФИО не найдено в тексте чека.")

    notes.append("Важно: бот проверяет формальные признаки чека. Поступление денег подтверждается админом по выписке/ЕРИП.")

    if risk_count:
        status = "flagged"
    elif manual_required:
        status = "needs_manual_review"
    else:
        status = "ready_for_admin_approval"

    return status, json.dumps(notes, ensure_ascii=False)
