import asyncio
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402
from aiogram.types import MenuButtonWebApp, WebAppInfo  # noqa: E402

from app.config import get_settings  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("chat_id", nargs="?", type=int)
    parser.add_argument("--url", dest="webapp_url")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    webapp_url = args.webapp_url or settings.webapp_url
    if not webapp_url.startswith("https://"):
        raise RuntimeError("Telegram Mini Apps require WEBAPP_URL to start with https://")

    menu_button = MenuButtonWebApp(
        text="Анкета БФБ",
        web_app=WebAppInfo(url=webapp_url),
    )

    bot = Bot(settings.bot_token)
    try:
        await bot.set_chat_menu_button(chat_id=args.chat_id, menu_button=menu_button)
        target = f"chat {args.chat_id}" if args.chat_id else "default bot menu"
        print(f"MiniApp menu button set for {target}: {webapp_url}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
