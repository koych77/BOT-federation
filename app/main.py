from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aiogram import Bot
from aiogram.types import Update
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
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
    path = forms_dir / "zayavlenie-na-vstuplenie-v-bfb.doc"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Бланк заявления не найден.")
    return FileResponse(
        path,
        media_type="application/msword",
        filename="zayavlenie-na-vstuplenie-v-bfb.doc",
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
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Некорректная дата: {raw}") from exc


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=f"Некорректная сумма: {raw}") from exc


@app.post("/api/applications")
async def create_application(
    init_data: str = Form(""),
    full_name: str = Form(...),
    birth_date: str | None = Form(None),
    phone: str = Form(...),
    email: str | None = Form(None),
    city: str = Form(...),
    club: str | None = Form(None),
    coach: str | None = Form(None),
    role: str = Form(...),
    application_type: str = Form(...),
    fee_type: str = Form(...),
    paid_amount: str | None = Form(None),
    payment_date: str | None = Form(None),
    payer_full_name: str = Form(...),
    operation_id: str | None = Form(None),
    payment_channel: str | None = Form(None),
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

    if not personal_data_consent or not data_accuracy_confirmed:
        raise HTTPException(status_code=422, detail="Нужно подтвердить согласия перед отправкой.")

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

    auto_status, auto_notes = run_preliminary_checks(
        db,
        fee_type=fee_type,
        expected_amount=expected_amount,
        paid_amount=parsed_paid_amount,
        payment_date=parsed_payment_date,
        payer_full_name=payer_full_name,
        member_full_name=full_name,
        operation_id=operation_id,
        receipt_sha256=receipt_sha256,
        receipt_size=receipt_size,
        content_type=receipt.content_type or "application/octet-stream",
        original_name=receipt.filename or "receipt",
        max_upload_bytes=settings.max_upload_bytes,
        receipt_scan_status=receipt_scan.status,
        receipt_scan_notes=receipt_scan.notes,
        receipt_text_has_amount=text_contains_amount(receipt_scan.text, parsed_paid_amount),
        receipt_text_has_operation=text_contains_operation(receipt_scan.text, operation_id),
        receipt_text_has_name=text_contains_name_part(receipt_scan.text, payer_full_name or full_name),
    )

    application = MemberApplication(
        telegram_id=telegram_user.get("id"),
        telegram_username=telegram_user.get("username"),
        telegram_first_name=telegram_user.get("first_name"),
        telegram_last_name=telegram_user.get("last_name"),
        full_name=full_name.strip(),
        birth_date=_parse_date(birth_date),
        phone=phone.strip(),
        email=email.strip() if email else None,
        city=city.strip(),
        club=club.strip() if club else None,
        coach=coach.strip() if coach else None,
        role=role,
        application_type=application_type,
        membership_year=settings.membership_year,
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
        payer_full_name=payer_full_name.strip(),
        operation_id=operation_id.strip() if operation_id else None,
        payment_channel=payment_channel.strip() if payment_channel else None,
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
        "message": "Заявка отправлена. Бот выполнил первичную проверку чека, администратор получит статус и примет финальное решение.",
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
