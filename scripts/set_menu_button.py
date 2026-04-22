import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402
from aiogram.types import MenuButtonWebApp, WebAppInfo  # noqa: E402

from app.config import get_settings  # noqa: E402


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    if not settings.webapp_url.startswith("https://"):
        raise RuntimeError("Telegram Mini Apps require WEBAPP_URL to start with https://")

    chat_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    menu_button = MenuButtonWebApp(
        text="Анкета БФБ",
        web_app=WebAppInfo(url=settings.webapp_url),
    )

    bot = Bot(settings.bot_token)
    try:
        await bot.set_chat_menu_button(chat_id=chat_id, menu_button=menu_button)
        target = f"chat {chat_id}" if chat_id else "default bot menu"
        print(f"MiniApp menu button set for {target}: {settings.webapp_url}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
