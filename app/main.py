from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, Update
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.bot import build_dispatcher, notify_admins
from app.config import get_settings
from app.db import get_db, init_db
from app.models import MemberApplication, Payment
from app.security import parse_telegram_init_data
from app.services.export import build_members_export
from app.services.payment_checks import expected_amount_for, run_preliminary_checks
from app.services.receipt_scanner import (
    scan_receipt_text,
    text_contains_amount,
    text_contains_name_part,
    text_contains_operation,
)
from app.services.storage import read_receipt_bytes, save_upload

settings = get_settings()
app = FastAPI(title=settings.app_name)
dispatcher = build_dispatcher()

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
forms_dir = Path(__file__).resolve().parent.parent / "assets" / "forms"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

ALLOWED_ROLES = {"presidium", "dancer", "trainer", "veteran", "organizer", "dj", "mc", "photo_video", "other"}


class FormDocumentRequest(BaseModel):
    initData: str = ""


@app.on_event("startup")
async def startup() -> None:
    init_db()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.bot_token and settings.webhook_url:
        bot = Bot(settings.bot_token)
        try:
            await bot.set_webhook(settings.webhook_url, drop_pending_updates=True)
        finally:
            await bot.session.close()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.get("/forms/zayavlenie-na-vstuplenie-v-bfb.doc")
async def application_form_doc() -> FileResponse:
    return _application_form_file("inline")


@app.get("/forms/zayavlenie-na-vstuplenie-v-bfb/download")
async def download_application_form_doc() -> FileResponse:
    return _application_form_file("attachment")


@app.post("/api/request-form-doc")
async def request_application_form_doc(payload: FormDocumentRequest) -> dict:
    if not settings.bot_token:
        raise HTTPException(status_code=503, detail="Бот пока не настроен для отправки документов.")

    try:
        telegram_user = parse_telegram_init_data(payload.initData, settings.bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Не удалось подтвердить Telegram-пользователя.") from exc

    telegram_id = telegram_user.get("id")
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Откройте форму из Telegram-бота, чтобы получить бланк в чат.")

    path = forms_dir / "zayavlenie-na-vstuplenie-v-bfb.doc"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Бланк заявления не найден на сервере.")

    bot = Bot(settings.bot_token)
    try:
        await bot.send_document(
            telegram_id,
            FSInputFile(path, filename="zayavlenie-na-vstuplenie-v-bfb.doc"),
            caption="Бланк заявления отправлен в чат. Его нужно распечатать, подписать и передать администратору.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось отправить бланк в Telegram. Напишите боту команду /form.",
        ) from exc
    finally:
        await bot.session.close()

    return {"message": "Бланк отправлен в чат с ботом. Бумажный оригинал с подписью остается обязательным."}


def _application_form_file(content_disposition_type: str) -> FileResponse:
    path = forms_dir / "zayavlenie-na-vstuplenie-v-bfb.doc"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Бланк заявления не найден.")
    return FileResponse(
        path,
        media_type="application/msword",
        filename="zayavlenie-na-vstuplenie-v-bfb.doc",
        content_disposition_type=content_disposition_type,
    )


@app.get("/api/config")
async def config() -> dict:
    return {
        "membershipYear": settings.membership_year,
        "entryFee": settings.entry_fee,
        "membershipFee": settings.membership_fee,
        "currency": settings.currency,
        "requireTelegramAuth": settings.require_telegram_auth,
    }


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    try:
        day, month, year = raw.replace("/", ".").replace("-", ".").split(".")
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Некорректная дата: {raw}. Используйте формат дд.мм.гггг.") from exc


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=f"Некорректная сумма: {raw}") from exc


def _clean(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    return cleaned or None


def _join_name(last_name: str | None, first_name: str | None, middle_name: str | None) -> str:
    return " ".join(part for part in [last_name, first_name, middle_name] if part)


def _requires_parent_consent(applicant_mode: str, birth_date_value: date | None) -> bool:
    if applicant_mode == "child":
        return True
    if not birth_date_value:
        return False
    today = date.today()
    age = today.year - birth_date_value.year - (
        (today.month, today.day) < (birth_date_value.month, birth_date_value.day)
    )
    return age < 18


@app.post("/api/applications")
async def create_application(
    init_data: str = Form(""),
    application_type: str = Form(...),
    applicant_mode: str = Form(...),
    applicant_last_name: str = Form(...),
    applicant_first_name: str = Form(...),
    applicant_middle_name: str | None = Form(None),
    citizenship: str | None = Form(None),
    member_last_name: str | None = Form(None),
    member_first_name: str | None = Form(None),
    member_middle_name: str | None = Form(None),
    birth_date: str | None = Form(None),
    region: str = Form(...),
    city: str = Form(...),
    street: str = Form(...),
    house: str = Form(...),
    apartment: str | None = Form(None),
    phone_home: str | None = Form(None),
    phone_mobile: str = Form(...),
    email: str | None = Form(None),
    workplace: str | None = Form(None),
    passport_number: str | None = Form(None),
    passport_issued_by: str | None = Form(None),
    statement_date: str | None = Form(None),
    mother_full_name: str | None = Form(None),
    mother_workplace_position: str | None = Form(None),
    father_full_name: str | None = Form(None),
    father_workplace_position: str | None = Form(None),
    role: str | None = Form(None),
    role_other: str | None = Form(None),
    fee_type: str = Form(...),
    paid_amount: str | None = Form(None),
    payment_date: str | None = Form(None),
    payer_full_name: str = Form(...),
    operation_id: str | None = Form(None),
    payment_channel: str | None = Form(None),
    statute_accepted: bool = Form(False),
    personal_data_consent: bool = Form(...),
    data_accuracy_confirmed: bool = Form(...),
    receipt: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if settings.require_telegram_auth and not init_data:
        raise HTTPException(status_code=401, detail="Откройте форму из Telegram-бота.")

    try:
        telegram_user = parse_telegram_init_data(init_data, settings.bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if not statute_accepted:
        raise HTTPException(status_code=422, detail="Нужно подтвердить, что заявитель ознакомлен с Уставом объединения.")

    if not personal_data_consent or not data_accuracy_confirmed:
        raise HTTPException(status_code=422, detail="Нужно подтвердить согласия перед отправкой.")

    applicant_mode = _clean(applicant_mode) or "self"
    if applicant_mode not in {"self", "child"}:
        raise HTTPException(status_code=422, detail="Некорректный тип заявителя.")

    application_type = _clean(application_type) or "entry"
    if application_type not in {"entry", "renewal"}:
        raise HTTPException(status_code=422, detail="Некорректный тип заявления.")

    applicant_last_name = _clean(applicant_last_name)
    applicant_first_name = _clean(applicant_first_name)
    applicant_middle_name = _clean(applicant_middle_name)
    if not applicant_last_name or not applicant_first_name:
        raise HTTPException(status_code=422, detail="Укажите фамилию и имя заявителя.")

    citizenship = _clean(citizenship) or "Республика Беларусь"

    member_last_name = _clean(member_last_name) or applicant_last_name
    member_first_name = _clean(member_first_name) or applicant_first_name
    member_middle_name = _clean(member_middle_name) or applicant_middle_name

    if applicant_mode == "child" and (not member_last_name or not member_first_name):
        raise HTTPException(status_code=422, detail="Для заявления за ребенка укажите фамилию и имя члена федерации.")

    parsed_birth_date = _parse_date(birth_date)
    parsed_statement_date = _parse_date(statement_date)
    member_full_name = _join_name(member_last_name, member_first_name, member_middle_name)
    applicant_full_name = _join_name(applicant_last_name, applicant_first_name, applicant_middle_name)

    mother_full_name = _clean(mother_full_name)
    mother_workplace_position = _clean(mother_workplace_position)
    father_full_name = _clean(father_full_name)
    father_workplace_position = _clean(father_workplace_position)
    role = _clean(role) or "dancer"
    role_other = _clean(role_other)
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail="Некорректная категория по бланку заявления.")
    if role == "other" and not role_other:
        raise HTTPException(status_code=422, detail="Для категории «Иное» укажите пояснение.")

    if _requires_parent_consent(applicant_mode, parsed_birth_date) and not (mother_full_name or father_full_name):
        raise HTTPException(
            status_code=422,
            detail="Для несовершеннолетнего нужно указать данные хотя бы одного родителя или законного представителя.",
        )

    expected_amount = expected_amount_for(fee_type, settings.entry_fee, settings.membership_fee)
    parsed_paid_amount = _parse_decimal(paid_amount)
    parsed_payment_date = _parse_date(payment_date)
    receipt_path, receipt_size, receipt_sha256 = await save_upload(settings, receipt)
    receipt_bytes = read_receipt_bytes(settings, receipt_path)
    receipt_scan = scan_receipt_text(
        receipt_bytes,
        receipt.content_type or "application/octet-stream",
        receipt.filename or "receipt",
    )

    payer_full_name = _clean(payer_full_name)
    if not payer_full_name:
        raise HTTPException(status_code=422, detail="Укажите ФИО плательщика.")

    auto_status, auto_notes = run_preliminary_checks(
        db,
        fee_type=fee_type,
        expected_amount=expected_amount,
        paid_amount=parsed_paid_amount,
        payment_date=parsed_payment_date,
        payer_full_name=payer_full_name,
        member_full_name=member_full_name,
        operation_id=_clean(operation_id),
        receipt_sha256=receipt_sha256,
        receipt_size=receipt_size,
        content_type=receipt.content_type or "application/octet-stream",
        original_name=receipt.filename or "receipt",
        max_upload_bytes=settings.max_upload_bytes,
        receipt_scan_status=receipt_scan.status,
        receipt_scan_notes=receipt_scan.notes,
        receipt_text_has_amount=text_contains_amount(receipt_scan.text, parsed_paid_amount),
        receipt_text_has_operation=text_contains_operation(receipt_scan.text, _clean(operation_id)),
        receipt_text_has_name=text_contains_name_part(receipt_scan.text, payer_full_name or member_full_name),
    )

    application = MemberApplication(
        telegram_id=telegram_user.get("id"),
        telegram_username=telegram_user.get("username"),
        telegram_first_name=telegram_user.get("first_name"),
        telegram_last_name=telegram_user.get("last_name"),
        applicant_mode=applicant_mode,
        applicant_last_name=applicant_last_name,
        applicant_first_name=applicant_first_name,
        applicant_middle_name=applicant_middle_name,
        citizenship=citizenship,
        member_last_name=member_last_name,
        member_first_name=member_first_name,
        member_middle_name=member_middle_name,
        full_name=member_full_name,
        birth_date=parsed_birth_date,
        region=_clean(region),
        phone=_clean(phone_mobile) or "",
        phone_home=_clean(phone_home),
        phone_mobile=_clean(phone_mobile),
        email=_clean(email),
        city=_clean(city) or "",
        street=_clean(street),
        house=_clean(house),
        apartment=_clean(apartment),
        passport_number=_clean(passport_number),
        passport_issued_by=_clean(passport_issued_by),
        statement_date=parsed_statement_date,
        club=None,
        coach=None,
        role=role,
        role_other=role_other,
        workplace=_clean(workplace),
        mother_full_name=mother_full_name,
        mother_workplace_position=mother_workplace_position,
        father_full_name=father_full_name,
        father_workplace_position=father_workplace_position,
        application_type=application_type,
        membership_year=settings.membership_year,
        statute_accepted=statute_accepted,
        personal_data_consent=personal_data_consent,
        data_accuracy_confirmed=data_accuracy_confirmed,
        status="submitted",
    )
    db.add(application)
    db.flush()

    payment = Payment(
        application_id=application.id,
        fee_type=fee_type,
        expected_amount=expected_amount,
        paid_amount=parsed_paid_amount,
        payment_date=parsed_payment_date,
        payer_full_name=payer_full_name,
        operation_id=_clean(operation_id),
        payment_channel=_clean(payment_channel),
        receipt_original_name=receipt.filename or "receipt",
        receipt_content_type=receipt.content_type or "application/octet-stream",
        receipt_size=receipt_size,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        auto_check_status=auto_status,
        auto_check_notes=auto_notes,
        admin_status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(application)
    db.refresh(payment)

    await notify_admins(application, payment, db)

    return {
        "id": application.id,
        "status": application.status,
        "autoCheckStatus": payment.auto_check_status,
        "memberFullName": member_full_name,
        "applicantFullName": applicant_full_name,
        "message": (
            "Заявление и чек отправлены. Бот выполнил первичную проверку оплаты. "
            "Дальше администратор сверит платеж, а бумажный оригинал заявления нужно передать отдельно."
        ),
    }


@app.get("/admin/export.xlsx")
async def export_excel(token: str | None = None, db: Session = Depends(get_db)) -> Response:
    if settings.public_base_url and not settings.admin_export_token:
        raise HTTPException(status_code=503, detail="Для публичного экспорта задайте ADMIN_EXPORT_TOKEN.")
    if settings.admin_export_token and token != settings.admin_export_token:
        raise HTTPException(status_code=403, detail="Неверный токен экспорта.")

    content = build_members_export(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bfb_members.xlsx"'},
    )


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict:
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not settings.bot_token:
        raise HTTPException(status_code=503, detail="BOT_TOKEN is not configured")

    bot = Bot(settings.bot_token)
    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()
    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    return {"ok": True}
