"""
Сервис отправки push-уведомлений через Expo Push API.
Документация: https://docs.expo.dev/push-notifications/sending-notifications/
"""
import logging
from typing import Optional, Any
import httpx

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_expo_push(
    *,
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
    sound: str = "default",
) -> bool:
    """
    Отправить одно push-уведомление через Expo Push API.
    Возвращает True при успехе, False при ошибке.
    При DeviceNotRegistered возвращает False (токен надо удалить — вызывающий код должен это обработать).
    """
    payload: dict[str, Any] = {
        "to": token,
        "title": title,
        "body": body,
        "sound": sound,
    }
    if data:
        payload["data"] = data

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()
            ticket = result.get("data", [{}])[0]
            if ticket.get("status") == "ok":
                logger.debug(f"[expo_push] OK, ticket_id={ticket.get('id')}, token={token[:30]}…")
                return True
            else:
                error = ticket.get("details", {}).get("error", "unknown")
                logger.warning(f"[expo_push] status={ticket.get('status')}, error={error}, token={token[:30]}…")
                if error == "DeviceNotRegistered":
                    raise DeviceNotRegisteredError(token)
                return False
    except DeviceNotRegisteredError:
        raise
    except Exception as exc:
        logger.error(f"[expo_push] request failed: {exc}", exc_info=True)
        return False


async def send_expo_push_batch(messages: list[dict]) -> list[dict]:
    """
    Отправить батч уведомлений (до 100 штук).
    Каждый элемент: {"to": ..., "title": ..., "body": ..., "data": ..., "sound": ...}
    Возвращает список tickets из ответа Expo.
    """
    if not messages:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
    except Exception as exc:
        logger.error(f"[expo_push_batch] request failed: {exc}", exc_info=True)
        return []


class DeviceNotRegisteredError(Exception):
    """Токен невалиден — устройство больше не зарегистрировано в Expo."""
    def __init__(self, token: str):
        self.token = token
        super().__init__(f"DeviceNotRegistered: {token}")

