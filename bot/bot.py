import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost")  # ngrok URL во время разработки

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()


def play_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="▶  Play SN▓KE",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]])


@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or "Player"
    await message.answer(
        f"Hey, {name}.\n\n"
        f"<b>SN▓KE</b> — online snake with leaderboard.\n\n"
        f"◉ Eat to grow\n"
        f"◆ Rare items give big bonuses\n"
        f"↯ Charge doubles your speed\n"
        f"❋ Frost slows time\n"
        f"✕ Poison shrinks you\n"
        f"◎ Relic: shrink for points\n\n"
        f"Your scores go to the global board.",
        parse_mode="HTML",
        reply_markup=play_keyboard(),
    )


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")
    logging.info(f"Bot started · webapp={WEBAPP_URL}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
