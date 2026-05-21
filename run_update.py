import asyncio
import argparse
import os
from sqlalchemy import select
from src.db.deps import get_db
from src.projects.models import Project

DEFAULT_PID = os.getenv("DEFAULT_PROJECT_ID")
DEFAULT_CHAT = os.getenv("TELEGRAM_CHAT_ID")


def parse_default_pid(value: str | None) -> int | None:
    """✅ Безопасное преобразование DEFAULT_PROJECT_ID в int."""
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        print(f"⚠️ Некорректное значение DEFAULT_PROJECT_ID='{value}', будет проигнорировано.")
        return None


async def main(project_id: int, telegram_chat_id: str):
    db_gen = get_db()
    db = await anext(db_gen)

    try:
        res = await db.execute(select(Project).where(Project.id == project_id))
        p = res.scalars().first()

        if p:
            p.telegram_chat_id = telegram_chat_id
            await db.commit()
            print(f"✅ УСПЕХ! Chat ID {telegram_chat_id} привязан к проекту ID {project_id}.")
        else:
            print(f"❌ Проект с ID {project_id} не найден.")
    finally:
        await db.close()


if __name__ == "__main__":
    default_pid = parse_default_pid(DEFAULT_PID)

    parser = argparse.ArgumentParser(description="Привязать Telegram Chat ID к проекту")

    parser.add_argument("--project-id",
                        type=int,
                        default=default_pid,
                        required=default_pid is None,
                        help="ID проекта (можно задать через DEFAULT_PROJECT_ID)")

    parser.add_argument("--chat-id",
                        type=str,
                        default=DEFAULT_CHAT,
                        required=DEFAULT_CHAT is None,
                        help="Telegram Chat ID (можно задать через TELEGRAM_CHAT_ID)")

    args = parser.parse_args()

    asyncio.run(main(project_id=args.project_id, telegram_chat_id=args.chat_id))