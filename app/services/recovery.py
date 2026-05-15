from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import MemberApplication, Payment
from app.services.snapshots import write_application_snapshot


@dataclass(frozen=True)
class RecoveredApplication:
    source_number: str
    application_type: str
    applicant_mode: str
    applicant_last_name: str | None
    applicant_first_name: str | None
    applicant_middle_name: str | None
    citizenship: str | None
    member_last_name: str | None
    member_first_name: str | None
    member_middle_name: str | None
    full_name: str
    birth_date: date | None
    region: str | None
    city: str
    street: str | None
    house: str | None
    apartment: str | None
    phone_mobile: str
    phone_home: str | None
    email: str | None
    workplace: str | None
    passport_number: str | None
    passport_issued_by: str | None
    statement_date: date | None
    mother_full_name: str | None
    mother_workplace_position: str | None
    father_full_name: str | None
    father_workplace_position: str | None
    fee_type: str
    expected_amount: Decimal
    paid_amount: Decimal | None
    payment_date: date | None
    payer_full_name: str
    operation_id: str | None
    payment_channel: str | None
    auto_check_status: str
    auto_check_notes: list[str]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value in {"-", "—"}:
        return None
    return value


def _split_name(value: str | None) -> tuple[str | None, str | None, str | None]:
    value = _clean(value)
    if not value:
        return None, None, None
    parts = value.split()
    return (
        parts[0] if len(parts) > 0 else None,
        parts[1] if len(parts) > 1 else None,
        " ".join(parts[2:]) if len(parts) > 2 else None,
    )


def _parse_date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    if value.isdigit() and len(value) == 8:
        value = f"{value[:2]}.{value[2:4]}.{value[4:]}"
    day, month, year = value.replace("/", ".").replace("-", ".").split(".")
    return date(int(year), int(month), int(day))


def _parse_amounts(value: str | None) -> tuple[Decimal, Decimal]:
    numbers = re.findall(r"\d+(?:[.,]\d+)?", value or "")
    paid = Decimal(numbers[0].replace(",", ".")) if numbers else Decimal("0")
    expected = Decimal(numbers[1].replace(",", ".")) if len(numbers) > 1 else paid
    return paid.quantize(Decimal("0.01")), expected.quantize(Decimal("0.01"))


def _parse_address(value: str | None) -> tuple[str | None, str, str | None, str | None, str | None]:
    value = _clean(value)
    if not value:
        return None, "-", None, None, None

    pattern = re.compile(
        r"^(?P<region>.*?),\s*(?P<city>.*?),\s*(?P<street>.*?)(?:,\s*дом\s*(?P<house>.*?))?(?:,\s*кв\.\s*(?P<apartment>.*))?$",
        flags=re.IGNORECASE,
    )
    match = pattern.match(value)
    if not match:
        parts = [part.strip() for part in value.split(",")]
        return (
            parts[0] if len(parts) > 0 else None,
            parts[1] if len(parts) > 1 else "-",
            parts[2] if len(parts) > 2 else None,
            None,
            None,
        )
    return (
        _clean(match.group("region")),
        _clean(match.group("city")) or "-",
        _clean(match.group("street")),
        _clean(match.group("house")),
        _clean(match.group("apartment")),
    )


def _get_field(block: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in block.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _map_application_type(value: str | None) -> str:
    value = value or ""
    return "renewal" if "Продление" in value else "entry"


def _map_applicant_mode(value: str | None) -> str:
    value = value or ""
    return "child" if "ребен" in value.lower() else "self"


def _map_fee_type(value: str | None) -> str:
    value = value or ""
    has_entry = "Вступ" in value
    has_membership = "Член" in value
    if has_entry and has_membership:
        return "both"
    if has_entry:
        return "entry"
    return "membership"


def _map_auto_check_status(value: str | None) -> str:
    value = value or ""
    if "формальные признаки" in value or "финальная сверка" in value:
        return "ready_for_admin_approval"
    if "риск" in value.lower() or "несоответствие" in value.lower():
        return "flagged"
    return "needs_manual_review"


def parse_admin_chat_text(text: str) -> list[RecoveredApplication]:
    marker = "Новая заявка #"
    records: list[RecoveredApplication] = []
    for raw_part in text.split(marker)[1:]:
        block = marker + raw_part
        first_line = block.splitlines()[0]
        source_number = first_line.replace(marker, "").strip() or "?"

        applicant_full_name = _clean(_get_field(block, "Заявитель"))
        member_full_name = _clean(_get_field(block, "Член федерации")) or applicant_full_name or "Без имени"
        applicant_last, applicant_first, applicant_middle = _split_name(applicant_full_name)
        member_last, member_first, member_middle = _split_name(member_full_name)
        region, city, street, house, apartment = _parse_address(_get_field(block, "Адрес"))
        paid_amount, expected_amount = _parse_amounts(_get_field(block, "Сумма"))
        auto_notes = [
            line[2:].strip()
            for line in block.splitlines()
            if line.startswith("- ")
        ]

        records.append(
            RecoveredApplication(
                source_number=source_number,
                application_type=_map_application_type(_get_field(block, "Тип заявления")),
                applicant_mode=_map_applicant_mode(_get_field(block, "Тип заявителя")),
                applicant_last_name=applicant_last,
                applicant_first_name=applicant_first,
                applicant_middle_name=applicant_middle,
                citizenship=_clean(_get_field(block, "Гражданство")),
                member_last_name=member_last,
                member_first_name=member_first,
                member_middle_name=member_middle,
                full_name=member_full_name,
                birth_date=_parse_date(_get_field(block, "Дата рождения")),
                region=region,
                city=city,
                street=street,
                house=house,
                apartment=apartment,
                phone_mobile=_clean(_get_field(block, "Телефон мобильный")) or "-",
                phone_home=_clean(_get_field(block, "Телефон домашний")),
                email=_clean(_get_field(block, "E-mail")),
                workplace=_clean(_get_field(block, "Место работы / учебы")),
                passport_number=_clean(_get_field(block, "Паспорт №")),
                passport_issued_by=_clean(_get_field(block, "Паспорт выдан")),
                statement_date=_parse_date(_get_field(block, "Дата заявления")),
                mother_full_name=_clean(_get_field(block, "Мать / представитель")),
                mother_workplace_position=_clean(_get_field(block, "Мать: место работы, должность")),
                father_full_name=_clean(_get_field(block, "Отец / представитель")),
                father_workplace_position=_clean(_get_field(block, "Отец: место работы, должность")),
                fee_type=_map_fee_type(_get_field(block, "Назначение оплаты")),
                expected_amount=expected_amount,
                paid_amount=paid_amount,
                payment_date=_parse_date(_get_field(block, "Дата оплаты")),
                payer_full_name=_clean(_get_field(block, "Плательщик")) or member_full_name,
                operation_id=_clean(_get_field(block, "Операция")),
                payment_channel=_clean(_get_field(block, "Канал оплаты")),
                auto_check_status=_map_auto_check_status(_get_field(block, "Статус")),
                auto_check_notes=auto_notes
                or ["Восстановлено из текста Telegram-чата администратора. Чек нужно сверить вручную."],
            )
        )
    return records


def _dedupe_key(record: RecoveredApplication) -> tuple[str, str, str, str]:
    return (
        record.full_name.strip().casefold(),
        record.payment_date.isoformat() if record.payment_date else "",
        str(record.paid_amount or ""),
        record.fee_type,
    )


def recover_applications_from_chat_text(
    settings: Settings,
    db: Session,
    text: str,
    *,
    dry_run: bool = True,
) -> dict[str, object]:
    parsed = parse_admin_chat_text(text)
    existing_operations = {
        value
        for value in db.scalars(
            select(Payment.operation_id).where(
                Payment.operation_id.is_not(None),
                Payment.operation_id != "",
                Payment.operation_id != "-",
            )
        )
        if value
    }

    existing_payments = db.scalars(select(Payment).join(Payment.application)).all()
    existing_keys = {
        (
            payment.application.full_name.strip().casefold(),
            payment.payment_date.isoformat() if payment.payment_date else "",
            str(payment.paid_amount or ""),
            payment.fee_type,
        )
        for payment in existing_payments
    }

    seen_operations: set[str] = set()
    seen_keys: set[tuple[str, str, str, str]] = set()
    imported: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for record in parsed:
        operation_id = record.operation_id if record.operation_id not in {None, "-", ""} else None
        key = _dedupe_key(record)
        duplicate_reason: str | None = None
        if operation_id and (operation_id in existing_operations or operation_id in seen_operations):
            duplicate_reason = "duplicate_operation"
        elif key in existing_keys or key in seen_keys:
            duplicate_reason = "duplicate_member_payment"

        if duplicate_reason:
            skipped.append({"sourceNumber": record.source_number, "fullName": record.full_name, "reason": duplicate_reason})
            continue

        if dry_run:
            imported.append({"sourceNumber": record.source_number, "fullName": record.full_name})
            if operation_id:
                seen_operations.add(operation_id)
            seen_keys.add(key)
            continue

        application = MemberApplication(
            telegram_id=None,
            telegram_username=None,
            telegram_first_name=None,
            telegram_last_name=None,
            applicant_mode=record.applicant_mode,
            applicant_last_name=record.applicant_last_name,
            applicant_first_name=record.applicant_first_name,
            applicant_middle_name=record.applicant_middle_name,
            citizenship=record.citizenship,
            member_last_name=record.member_last_name,
            member_first_name=record.member_first_name,
            member_middle_name=record.member_middle_name,
            full_name=record.full_name,
            birth_date=record.birth_date,
            region=record.region,
            phone=record.phone_mobile,
            phone_home=record.phone_home,
            phone_mobile=record.phone_mobile,
            email=record.email,
            city=record.city,
            street=record.street,
            house=record.house,
            apartment=record.apartment,
            passport_number=record.passport_number,
            passport_issued_by=record.passport_issued_by,
            statement_date=record.statement_date,
            club=None,
            coach=None,
            role="member",
            role_other=None,
            workplace=record.workplace,
            mother_full_name=record.mother_full_name,
            mother_workplace_position=record.mother_workplace_position,
            father_full_name=record.father_full_name,
            father_workplace_position=record.father_workplace_position,
            application_type=record.application_type,
            membership_year=settings.membership_year,
            statute_accepted=False,
            personal_data_consent=True,
            data_accuracy_confirmed=True,
            status="recovered",
        )
        db.add(application)
        db.flush()

        payment = Payment(
            application_id=application.id,
            fee_type=record.fee_type,
            expected_amount=record.expected_amount,
            paid_amount=record.paid_amount,
            payment_date=record.payment_date,
            payer_full_name=record.payer_full_name,
            operation_id=operation_id,
            payment_channel=record.payment_channel,
            receipt_original_name="recovered-from-telegram-chat.txt",
            receipt_content_type="text/plain",
            receipt_size=0,
            receipt_path=f"recovered://telegram-chat/{record.source_number}",
            receipt_sha256=hashlib.sha256(f"{record.source_number}:{record.full_name}:{key}".encode("utf-8")).hexdigest(),
            auto_check_status=record.auto_check_status,
            auto_check_notes=json.dumps(record.auto_check_notes, ensure_ascii=False),
            admin_status="pending",
        )
        db.add(payment)
        db.flush()
        write_application_snapshot(settings, application, payment)

        imported.append({"sourceNumber": record.source_number, "fullName": record.full_name, "applicationId": application.id})
        if operation_id:
            seen_operations.add(operation_id)
        seen_keys.add(key)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "dryRun": dry_run,
        "parsed": len(parsed),
        "imported": len(imported),
        "skipped": len(skipped),
        "importedItems": imported,
        "skippedItems": skipped,
    }
