import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
# Импортируем DefaultBotProperties для совместимости с новой версией aiogram
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dp: Dispatcher | None = None


def get_bot() -> Bot:
    """Возвращает синглтон бота. Токен берётся из settings."""
    global _bot
    if _bot is None:
        from src.core.config import settings
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN не задан. "
                "Добавь его в .env и в класс Settings в config.py"
            )
        # Исправлено: теперь parse_mode передаётся через DefaultBotProperties
        _bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    return _bot


def get_dispatcher() -> Dispatcher:
    """Возвращает синглтон диспетчера с обработчиками."""
    global _dp
    if _dp is None:
        _dp = Dispatcher()

        # Обработчик когда бот добавляется в группу
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
    """Запускает polling бота для обработки событий."""
    bot = get_bot()
    dp = get_dispatcher()
    logger.info("Telegram: запуск polling...")
    await dp.start_polling(bot)


async def send_telegram_message(chat_id: str | int, text: str) -> bool:
    """
    Отправляет сообщение в Telegram-чат.
    Возвращает True при успехе, False при ошибке (не крашит приложение).
    """
    try:
        bot = get_bot()
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info("Telegram: сообщение отправлено в чат %s", chat_id)
        return True
    except Exception as exc:
        logger.error("Telegram: ошибка отправки в чат %s: %s", chat_id, exc)
        return False