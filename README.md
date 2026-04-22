# BFB Membership Telegram Mini App

MVP для приема заявок в Белорусскую федерацию брейкинга: Telegram bot, Mini App анкета, загрузка чеков, первичная проверка оплаты, ручное подтверждение администратора и экспорт в Excel.

## Возможности

- `/start` в Telegram открывает Mini App.
- Участник заполняет анкету и загружает чек оплаты.
- Backend сохраняет заявку, файл чека и результат первичной проверки.
- Администраторы получают Telegram-уведомление с кнопками подтверждения.
- Excel-выгрузка доступна по `/admin/export.xlsx`.

## Локальный запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Откройте `http://localhost:8000`.

## Railway

1. Создайте GitHub-репозиторий и отправьте туда код.
2. Создайте Railway project из GitHub repo.
3. Добавьте PostgreSQL plugin.
4. Заполните переменные окружения из `.env.example`.
5. Укажите Railway domain в `WEBAPP_URL` и `PUBLIC_BASE_URL`.
6. В BotFather настройте Mini App/Web App domain на домен Railway.

После запуска приложение само установит Telegram webhook, если заданы `BOT_TOKEN`, `PUBLIC_BASE_URL` и `TELEGRAM_WEBHOOK_SECRET`.

## Проверка оплат

Текущая проверка является предварительной: формат файла, размер, сумма, дата, ФИО, дубли по файлу и номеру операции. Для настоящего автоматического подтверждения нужно добавить сверку с банковской или ЕРИП-выпиской.
