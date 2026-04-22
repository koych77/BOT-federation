import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402

from app.bot import build_dispatcher  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db  # noqa: E402


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    init_db()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    bot = Bot(settings.bot_token)
    dispatcher = build_dispatcher()
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        print(f"Polling started for @{me.username}. Press Ctrl+C to stop.")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
