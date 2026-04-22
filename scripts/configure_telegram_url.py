import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo  # noqa: E402

from app.config import get_settings  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--admin-id", type=int, default=697068570)
    parser.add_argument("--set-webhook", action="store_true")
    args = parser.parse_args()

    public_url = args.url.rstrip("/")
    if not public_url.startswith("https://"):
        raise RuntimeError("Telegram Mini Apps require an https:// URL")

    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = Bot(settings.bot_token)
    try:
        menu_button = MenuButtonWebApp(text="Анкета БФБ", web_app=WebAppInfo(url=public_url))
        await bot.set_chat_menu_button(menu_button=menu_button)
        await bot.set_chat_menu_button(chat_id=args.admin_id, menu_button=menu_button)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть анкету БФБ", web_app=WebAppInfo(url=public_url))]
            ]
        )
        await bot.send_message(
            args.admin_id,
            f"Кнопка MiniApp обновлена на Railway:\n{public_url}",
            reply_markup=keyboard,
        )

        if args.set_webhook:
            webhook_url = f"{public_url}/telegram/webhook/{settings.telegram_webhook_secret}"
            await bot.set_webhook(webhook_url, drop_pending_updates=True)
            print(f"Webhook set: {webhook_url}")

        print(f"MiniApp URL configured: {public_url}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
