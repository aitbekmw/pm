import asyncio
import html
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_FILE_BASE = "https://api.telegram.org/file"
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

MAX_TELEGRAM_MESSAGE = 3900


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using %s", name, value, default)
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float for %s=%r, using %s", name, value, default)
        return default


def parse_csv_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_allowed_user_ids() -> set[int]:
    ids: set[int] = set()
    for raw_id in parse_csv_env("TELEGRAM_ALLOWED_USER_IDS"):
        try:
            ids.add(int(raw_id))
        except ValueError:
            logger.warning("Ignoring invalid TELEGRAM_ALLOWED_USER_IDS item: %r", raw_id)
    return ids


@dataclass(frozen=True)
class BotConfig:
    telegram_token: str
    elevenlabs_api_key: str
    whisper_url: str
    elevenlabs_model: str
    elevenlabs_diarize: bool
    elevenlabs_tag_audio_events: bool
    elevenlabs_timestamps_granularity: str
    elevenlabs_num_speakers: int | None
    elevenlabs_keyterms: list[str]
    request_timeout: float
    max_file_mb: int
    allowed_user_ids: set[int]

    @classmethod
    def from_env(cls) -> "BotConfig":
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        if not telegram_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        if not elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is required")

        num_speakers = env_int("ELEVENLABS_NUM_SPEAKERS", 0)
        return cls(
            telegram_token=telegram_token,
            elevenlabs_api_key=elevenlabs_api_key,
            whisper_url=os.getenv(
                "WHISPER_SERVER_URL",
                "http://10.0.10.3:8000/transcribe",
            ).strip(),
            elevenlabs_model=os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2").strip(),
            elevenlabs_diarize=env_bool("ELEVENLABS_DIARIZE", True),
            elevenlabs_tag_audio_events=env_bool("ELEVENLABS_TAG_AUDIO_EVENTS", True),
            elevenlabs_timestamps_granularity=os.getenv(
                "ELEVENLABS_TIMESTAMPS_GRANULARITY",
                "word",
            ).strip(),
            elevenlabs_num_speakers=num_speakers if num_speakers > 0 else None,
            elevenlabs_keyterms=parse_csv_env("ELEVENLABS_KEYTERMS"),
            request_timeout=env_float("BOT_REQUEST_TIMEOUT_SECONDS", 900.0),
            max_file_mb=env_int("BOT_MAX_FILE_MB", 50),
            allowed_user_ids=parse_allowed_user_ids(),
        )


class TelegramAPI:
    def __init__(self, token: str, client: httpx.AsyncClient) -> None:
        self.token = token
        self.client = client

    async def call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self.client.post(
            f"{TELEGRAM_API_BASE}/bot{self.token}/{method}",
            json=payload or {},
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data}")
        return data["result"]

    async def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": 45,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        return await self.call("getUpdates", payload)

    async def send_message(self, chat_id: int, text: str) -> None:
        for chunk in split_text(text, MAX_TELEGRAM_MESSAGE):
            await self.call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        await self.call("sendChatAction", {"chat_id": chat_id, "action": action})

    async def download_file(self, file_id: str) -> bytes:
        file_info = await self.call("getFile", {"file_id": file_id})
        file_path = file_info["file_path"]
        response = await self.client.get(
            f"{TELEGRAM_FILE_BASE}/bot{self.token}/{file_path}",
        )
        response.raise_for_status()
        return response.content


def split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def format_seconds(seconds: int | float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def approx_cost(duration_seconds: int | float | None) -> str:
    if not duration_seconds:
        return ""
    cost = float(duration_seconds) / 3600 * 0.22
    return f" / ~${cost:.4f} при $0.22/ч"


def extract_audio_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if "voice" in message:
        audio = message["voice"]
        return {
            "kind": "voice",
            "file_id": audio["file_id"],
            "file_name": "telegram_voice.ogg",
            "mime_type": audio.get("mime_type") or "audio/ogg",
            "duration": audio.get("duration"),
            "file_size": audio.get("file_size"),
        }
    if "audio" in message:
        audio = message["audio"]
        return {
            "kind": "audio",
            "file_id": audio["file_id"],
            "file_name": audio.get("file_name") or "telegram_audio",
            "mime_type": audio.get("mime_type") or "application/octet-stream",
            "duration": audio.get("duration"),
            "file_size": audio.get("file_size"),
        }
    if "document" in message:
        document = message["document"]
        mime_type = document.get("mime_type") or ""
        file_name = document.get("file_name") or "telegram_document"
        if not (mime_type.startswith("audio/") or mime_type.startswith("video/")):
            suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
            if suffix not in {"mp3", "wav", "m4a", "ogg", "oga", "opus", "flac", "mp4", "webm"}:
                return None
        return {
            "kind": "document",
            "file_id": document["file_id"],
            "file_name": file_name,
            "mime_type": mime_type or "application/octet-stream",
            "duration": None,
            "file_size": document.get("file_size"),
        }
    return None


async def transcribe_elevenlabs(
    client: httpx.AsyncClient,
    config: BotConfig,
    audio_bytes: bytes,
    filename: str,
    mime_type: str,
) -> dict[str, Any]:
    form_parts = [
        ("model_id", (None, config.elevenlabs_model)),
        ("diarize", (None, str(config.elevenlabs_diarize).lower())),
        ("tag_audio_events", (None, str(config.elevenlabs_tag_audio_events).lower())),
        ("timestamps_granularity", (None, config.elevenlabs_timestamps_granularity)),
    ]
    if config.elevenlabs_num_speakers:
        form_parts.append(("num_speakers", (None, str(config.elevenlabs_num_speakers))))
    for keyterm in config.elevenlabs_keyterms:
        form_parts.append(("keyterms", (None, keyterm)))
    form_parts.append(("file", (filename, audio_bytes, mime_type)))

    response = await client.post(
        ELEVENLABS_STT_URL,
        headers={"xi-api-key": config.elevenlabs_api_key},
        files=form_parts,
    )
    response.raise_for_status()
    return response.json()


async def transcribe_whisper(
    client: httpx.AsyncClient,
    config: BotConfig,
    audio_bytes: bytes,
    filename: str,
    mime_type: str,
) -> dict[str, Any] | list[dict[str, Any]]:
    response = await client.post(
        config.whisper_url,
        files={"file": (filename, audio_bytes, mime_type)},
    )
    response.raise_for_status()
    return response.json()


def text_from_whisper(result: dict[str, Any] | list[dict[str, Any]]) -> str:
    if isinstance(result, list):
        return " ".join(
            str(item.get("text", "")).strip()
            for item in result
            if isinstance(item, dict)
        ).strip()
    text = str(result.get("text", "")).strip()
    if text:
        return text
    segments = result.get("segments", [])
    if isinstance(segments, list):
        return " ".join(
            str(item.get("text", "")).strip()
            for item in segments
            if isinstance(item, dict)
        ).strip()
    return ""


def normalize_token(text: str) -> str:
    text = text or ""
    if not text:
        return ""
    if re.fullmatch(r"[\s]+", text):
        return " "
    return text.strip()


def append_token(current: str, token: str) -> str:
    token = normalize_token(token)
    if not token:
        return current
    if not current:
        return token.strip()
    if token in {".", ",", "!", "?", ":", ";", "%", ")", "]", "}"}:
        return current.rstrip() + token
    if token in {"(", "[", "{"}:
        return current.rstrip() + " " + token
    if current.endswith((" ", "(", "[", "{")):
        return current + token
    return current + " " + token


def speaker_label(speaker_id: str | None, aliases: dict[str, str]) -> str:
    if not speaker_id:
        return "Speaker"
    if speaker_id not in aliases:
        aliases[speaker_id] = f"Speaker {len(aliases) + 1}"
    return aliases[speaker_id]


def diarized_text_from_elevenlabs(result: dict[str, Any]) -> str:
    words = result.get("words")
    if not isinstance(words, list) or not words:
        return str(result.get("text", "")).strip()

    aliases: dict[str, str] = {}
    blocks: list[tuple[str, str]] = []
    current_speaker: str | None = None
    current_text = ""

    for item in words:
        if not isinstance(item, dict):
            continue
        token = str(item.get("text", ""))
        token_type = item.get("type")
        speaker_id = item.get("speaker_id")
        if token_type in {"spacing"}:
            current_text = append_token(current_text, token)
            continue

        if speaker_id != current_speaker and current_text.strip():
            blocks.append((speaker_label(current_speaker, aliases), current_text.strip()))
            current_text = ""
        current_speaker = speaker_id
        current_text = append_token(current_text, token)

    if current_text.strip():
        blocks.append((speaker_label(current_speaker, aliases), current_text.strip()))

    if not blocks:
        return str(result.get("text", "")).strip()

    return "\n".join(f"{speaker}: {text}" for speaker, text in blocks)


def format_elevenlabs_metadata(result: dict[str, Any]) -> str:
    language = result.get("language_code")
    probability = result.get("language_probability")
    parts = []
    if language:
        parts.append(f"language={language}")
    if isinstance(probability, int | float):
        parts.append(f"probability={probability:.2f}")
    return ", ".join(parts)


async def process_audio_message(
    telegram: TelegramAPI,
    client: httpx.AsyncClient,
    config: BotConfig,
    message: dict[str, Any],
) -> None:
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id")

    if config.allowed_user_ids and user_id not in config.allowed_user_ids:
        await telegram.send_message(chat_id, "Доступ для этого Telegram user_id закрыт.")
        return

    audio = extract_audio_message(message)
    if not audio:
        await telegram.send_message(
            chat_id,
            "Отправьте голосовое сообщение, аудиофайл или audio/video document.",
        )
        return

    file_size = audio.get("file_size")
    max_bytes = config.max_file_mb * 1024 * 1024
    if file_size and file_size > max_bytes:
        await telegram.send_message(
            chat_id,
            (
                f"Файл слишком большой: {file_size / 1024 / 1024:.1f} MB. "
                f"Лимит: {config.max_file_mb} MB."
            ),
        )
        return

    duration = audio.get("duration")
    await telegram.send_chat_action(chat_id, "typing")
    await telegram.send_message(
        chat_id,
        (
            "Аудио получено. Запускаю ElevenLabs Scribe v2 и текущий Whisper параллельно.\n"
            f"Длительность: {format_seconds(duration)}{approx_cost(duration)}"
        ),
    )

    audio_bytes = await telegram.download_file(audio["file_id"])
    if len(audio_bytes) > max_bytes:
        file_mb = len(audio_bytes) / 1024 / 1024
        await telegram.send_message(
            chat_id,
            (
                f"Скачанный файл слишком большой: {file_mb:.1f} MB. "
                f"Лимит: {config.max_file_mb} MB."
            ),
        )
        return

    filename = audio["file_name"]
    mime_type = audio["mime_type"]

    start = time.monotonic()
    eleven_task = asyncio.create_task(
        transcribe_elevenlabs(client, config, audio_bytes, filename, mime_type)
    )
    whisper_task = asyncio.create_task(
        transcribe_whisper(client, config, audio_bytes, filename, mime_type)
    )
    eleven_result, whisper_result = await asyncio.gather(
        eleven_task,
        whisper_task,
        return_exceptions=True,
    )
    elapsed = time.monotonic() - start

    lines = [f"<b>Готово за {elapsed:.1f}s</b>"]

    lines.append("\n<b>ElevenLabs Scribe v2</b>")
    if isinstance(eleven_result, Exception):
        logger.exception("ElevenLabs transcription failed", exc_info=eleven_result)
        lines.append(f"Ошибка: {html.escape(str(eleven_result))}")
    else:
        meta = format_elevenlabs_metadata(eleven_result)
        if meta:
            lines.append(f"<i>{html.escape(meta)}</i>")
        lines.append(html.escape(diarized_text_from_elevenlabs(eleven_result) or "(empty)"))

    lines.append("\n<b>Текущий Whisper</b>")
    if isinstance(whisper_result, Exception):
        logger.exception("Whisper transcription failed", exc_info=whisper_result)
        lines.append(f"Ошибка: {html.escape(str(whisper_result))}")
    else:
        lines.append(html.escape(text_from_whisper(whisper_result) or "(empty)"))

    await telegram.send_message(chat_id, "\n".join(lines))


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    config = BotConfig.from_env()
    timeout = httpx.Timeout(config.request_timeout, connect=30.0)
    offset: int | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        telegram = TelegramAPI(config.telegram_token, client)
        me = await telegram.call("getMe")
        logger.info("Telegram compare bot started as @%s", me.get("username"))

        while True:
            try:
                updates = await telegram.get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message:
                        continue
                    try:
                        await process_audio_message(telegram, client, config, message)
                    except Exception as exc:
                        logger.exception("Failed to process update %s", update.get("update_id"))
                        chat_id = message.get("chat", {}).get("id")
                        if chat_id:
                            await telegram.send_message(
                                chat_id,
                                f"Ошибка обработки: {html.escape(str(exc))}",
                            )
            except Exception:
                logger.exception("Telegram polling failed; retrying in 5 seconds")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
