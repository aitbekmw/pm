import logging
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ChatMemberUpdated, Message
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, Command

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dp: Dispatcher | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        from src.core.config import settings
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN не задан. "
                "Добавь его в .env и в класс Settings в config.py"
            )
        _bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    return _bot


def get_dispatcher() -> Dispatcher:
    global _dp
    if _dp is None:
        _dp = Dispatcher()

        # ── /start ──────────────────────────────────────────────────────────
        @_dp.message(Command("start"))
        async def cmd_start(message: Message):
            await message.answer(
                "👋 Привет! Я <b>PM Assistant Bot</b>.\n\n"
                "Я помогаю уведомлять команду о встречах и задачах.\n\n"
                "📌 Чтобы подключить меня к проекту:\n"
                "1. Добавь меня в нужную группу\n"
                "2. Скопируй Chat ID группы\n"
                "3. Вставь его в настройках проекта\n\n"
                f"Твой Chat ID: <code>{message.chat.id}</code>"
            )

        # ── /help ────────────────────────────────────────────────────────────
        @_dp.message(Command("help"))
        async def cmd_help(message: Message):
            await message.answer(
                "ℹ️ <b>PM Assistant Bot</b>\n\n"
                "Доступные команды:\n"
                "/start — начало работы\n"
                "/chatid — узнать Chat ID этого чата\n"
                "/help — эта справка"
            )

        # ── /chatid ──────────────────────────────────────────────────────────
        @_dp.message(Command("chatid"))
        async def cmd_chatid(message: Message):
            await message.answer(
                f"Chat ID этого чата:\n<code>{message.chat.id}</code>"
            )

        # ── Бот добавлен в группу ────────────────────────────────────────────
        @_dp.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
        async def bot_added_to_group(event: ChatMemberUpdated):
            try:
                bot = get_bot()
                await bot.send_message(
                    chat_id=event.chat.id,
                    text=(
                        "👋 Привет! Я <b>PM Assistant Bot</b>.\n\n"
                        "Буду уведомлять вас о новых встречах в этом чате. 🗓\n\n"
                        "Чтобы подключить меня к проекту — укажите этот Chat ID "
                        "в настройках проекта:\n"
                        f"<code>{event.chat.id}</code>"
                    )
                )
                logger.info("Telegram: приветствие отправлено в чат %s", event.chat.id)
            except Exception as exc:
                logger.error("Telegram: ошибка приветствия в чат %s: %s", event.chat.id, exc)

    return _dp


async def start_bot_polling():
    bot = get_bot()
    dp = get_dispatcher()
    logger.info("Telegram: запуск polling...")
    await dp.start_polling(bot)


async def send_telegram_message(chat_id: str | int, text: str) -> bool:
    try:
        bot = get_bot()
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info("Telegram: сообщение отправлено в чат %s", chat_id)
        return True
    except Exception as exc:
        logger.error("Telegram: ошибка отправки в чат %s: %s", chat_id, exc)
        return False