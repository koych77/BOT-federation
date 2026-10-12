"""Cloudflare implementation of the federation bot and application form."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from js import fetch
from workers import asgi

app = FastAPI(title="Federation Bot (Cloudflare)")
Default = asgi.entrypoint(app)


def env_text(env, name: str, default: str = "") -> str:
    value = getattr(env, name, None)
    return str(value) if value is not None else default


async def ensure_schema(env) -> None:
    await env.DB.prepare("""
      CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id TEXT, telegram_username TEXT,
        applicant_name TEXT NOT NULL, member_name TEXT NOT NULL, phone TEXT NOT NULL,
        email TEXT, city TEXT NOT NULL, role TEXT, fee_type TEXT NOT NULL,
        paid_amount TEXT, payer_name TEXT NOT NULL, receipt_name TEXT,
        receipt_type TEXT, receipt_size INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'submitted',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    """).run()


def verify_init_data(init_data: str, token: str) -> dict:
    if not init_data:
        return {}
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    supplied_hash = values.pop("hash", "")
    if not supplied_hash:
        raise HTTPException(status_code=401, detail="Telegram authorization is missing")
    auth_date = int(values.get("auth_date", "0") or 0)
    if auth_date and abs(int(time.time()) - auth_date) > 86400:
        raise HTTPException(status_code=401, detail="Telegram authorization has expired")
    data_check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash):
        raise HTTPException(status_code=401, detail="Telegram authorization is invalid")
    try:
        return json.loads(values.get("user", "{}"))
    except json.JSONDecodeError:
        return {}


async def telegram_call(env, method: str, params: dict) -> None:
    token = env_text(env, "BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="BOT_TOKEN is not configured")
    response = await fetch(f"https://api.telegram.org/bot{token}/{method}?{urlencode(params)}")
    if not response.ok:
        raise HTTPException(status_code=502, detail="Telegram API request failed")


async def notify_admins(env, application_id: int, member_name: str, phone: str) -> None:
    text = f"Новая заявка #{application_id}\nФИО: {member_name}\nТелефон: {phone}"
    for admin_id in env_text(env, "ADMIN_TELEGRAM_IDS").replace(";", ",").split(","):
        if admin_id.strip():
            try:
                await telegram_call(env, "sendMessage", {"chat_id": admin_id.strip(), "text": text})
            except Exception:
                pass


@app.get("/health")
async def health(request: Request) -> dict:
    await ensure_schema(request.scope["env"])
    result = await request.scope["env"].DB.prepare("SELECT 1 AS ok").first()
    return {"ok": True, "database": "d1", "query": int(result.ok)}


@app.get("/api/config")
async def config(request: Request) -> dict:
    env = request.scope["env"]
    return {"membershipYear": int(env_text(env, "MEMBERSHIP_YEAR", "2026")),
            "entryFee": env_text(env, "ENTRY_FEE", "0"),
            "membershipFee": env_text(env, "MEMBERSHIP_FEE", "0"),
            "currency": env_text(env, "CURRENCY", "BYN"),
            "requireTelegramAuth": env_text(env, "REQUIRE_TELEGRAM_AUTH", "true").lower() == "true"}


@app.post("/api/applications")
async def create_application(request: Request) -> dict:
    env = request.scope["env"]
    await ensure_schema(env)
    form = await request.form()
    token = env_text(env, "BOT_TOKEN")
    user = verify_init_data(str(form.get("init_data", "")), token) if token else {}
    required = ["applicant_last_name", "applicant_first_name", "city", "phone_mobile", "fee_type", "payer_full_name"]
    if any(not str(form.get(name, "")).strip() for name in required):
        raise HTTPException(status_code=422, detail="Заполните обязательные поля формы.")
    applicant_name = " ".join(str(form.get(n, "")).strip() for n in
                              ("applicant_last_name", "applicant_first_name", "applicant_middle_name")
                              if str(form.get(n, "")).strip())
    member_name = " ".join(str(form.get(n, "")).strip() for n in
                           ("member_last_name", "member_first_name", "member_middle_name")
                           if str(form.get(n, "")).strip()) or applicant_name
    receipt = form.get("receipt")
    receipt_name = getattr(receipt, "filename", "") or ""
    receipt_type = getattr(receipt, "content_type", "") or ""
    receipt_size = len(await receipt.read()) if receipt and hasattr(receipt, "read") else 0
    payload = {key: str(value) for key, value in form.multi_items() if key != "receipt"}
    await env.DB.prepare("""
      INSERT INTO applications (telegram_id, telegram_username, applicant_name, member_name,
      phone, email, city, role, fee_type, paid_amount, payer_name, receipt_name, receipt_type,
      receipt_size, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """).bind(str(user.get("id", "")), str(user.get("username", "")), applicant_name, member_name,
      str(form.get("phone_mobile", "")).strip(), str(form.get("email", "")).strip(),
      str(form.get("city", "")).strip(), str(form.get("role", "member")).strip(),
      str(form.get("fee_type", "")).strip(), str(form.get("paid_amount", "")).strip(),
      str(form.get("payer_full_name", "")).strip(), receipt_name, receipt_type, receipt_size,
      json.dumps(payload, ensure_ascii=False)).run()
    row = await env.DB.prepare("SELECT last_insert_rowid() AS id").first()
    application_id = int(row.id)
    await notify_admins(env, application_id, member_name, str(form.get("phone_mobile", "")))
    return {"id": application_id, "status": "submitted", "autoCheckStatus": "pending",
            "memberFullName": member_name, "applicantFullName": applicant_name,
            "message": "Заявление принято. Администратор проверит данные и оплату."}


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict:
    env = request.scope["env"]
    if secret != env_text(env, "TELEGRAM_WEBHOOK_SECRET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = await request.json()
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    text = str(message.get("text", ""))
    if chat.get("id") and (text.startswith("/start") or text.startswith("/form")):
        webapp_url = env_text(env, "WEBAPP_URL", "https://federation-bot.koych77.workers.dev")
        menu_button = {"type": "web_app", "text": "Открыть анкету", "web_app": {"url": webapp_url}}
        await telegram_call(env, "setChatMenuButton", {
            "chat_id": str(chat["id"]),
            "menu_button": json.dumps(menu_button, ensure_ascii=False),
        })
        keyboard = {"inline_keyboard": [[{"text": "Открыть анкету", "web_app": {"url": webapp_url}}]]}
        await telegram_call(env, "sendMessage", {"chat_id": str(chat["id"]),
          "text": "Откройте анкету для вступления или продления членства в федерации.",
          "reply_markup": json.dumps(keyboard, ensure_ascii=False)})
    return {"ok": True}


@app.get("/{path:path}")
async def frontend(path: str, request: Request) -> Response:
    response = await request.scope["env"].ASSETS.fetch(f"https://assets.local/{path or 'index.html'}")
    return Response(content=await response.bytes(), status_code=response.status, headers=dict(response.headers))
