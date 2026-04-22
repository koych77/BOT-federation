# BFB Membership Telegram Mini App

MVP для приема заявок в Белорусскую федерацию брейкинга: Telegram bot, Mini App анкета, загрузка чеков, первичная проверка оплаты, ручное подтверждение администратора и экспорт в Excel.

## Возможности

- `/start` в Telegram открывает Mini App.
- Участник заполняет анкету и загружает чек оплаты.
- Backend сохраняет заявку, файл чека и результат первичной проверки.
- Для вступления доступен официальный бланк заявления: `/forms/zayavlenie-na-vstuplenie-v-bfb/download`.
- В Telegram бот может прислать бланк файлом по команде `/form`.
- PDF-чеки с машинно-читаемым текстом бот сканирует сам: ищет сумму, ФИО и номер операции.
- Фото и скрины чеков бот помечает как требующие ручной проверки.
- Администраторы получают Telegram-уведомление с кнопками подтверждения.
- Excel-выгрузка доступна по `/admin/export.xlsx`.
- Чеки можно хранить локально для разработки или в S3/Cloudflare R2 для Railway.

## Локальный запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Откройте `http://localhost:8000`.

Для локального теста Telegram-бота во втором терминале запустите polling:

```bash
.venv\Scripts\activate
python scripts/polling.py
```

После этого бот будет отвечать на `/start` и `/id` без публичного webhook.

## Railway

1. Создайте GitHub-репозиторий и отправьте туда код.
2. Создайте Railway project из GitHub repo.
3. Добавьте PostgreSQL plugin.
4. Заполните переменные окружения из `.env.example`.
5. Укажите Railway domain в `WEBAPP_URL` и `PUBLIC_BASE_URL`.
6. В BotFather настройте Mini App/Web App domain на домен Railway.

Для production на Railway лучше поставить `STORAGE_BACKEND=s3` и заполнить `STORAGE_ENDPOINT_URL`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`. Подойдет Cloudflare R2 или любой S3-compatible storage.

После запуска приложение само установит Telegram webhook, если заданы `BOT_TOKEN`, `PUBLIC_BASE_URL` и `TELEGRAM_WEBHOOK_SECRET`.

### Быстрый деплой через CLI

Сначала войдите в Railway в обычном терминале:

```bash
railway login
```

Потом запустите:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\railway_deploy.ps1
```

Скрипт создаст проект, сервис, PostgreSQL, Railway-домен, выставит переменные, задеплоит приложение и обновит кнопку Mini App в Telegram.

## Проверка оплат

Текущая проверка является предварительной: формат файла, размер, сумма, дата, ФИО, дубли по файлу и номеру операции. PDF с текстом дополнительно сканируется. Для настоящего автоматического подтверждения поступления денег нужно добавить сверку с банковской или ЕРИП-выпиской.
