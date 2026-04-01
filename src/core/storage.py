import asyncio
import io
import json
import logging
import mimetypes
import os
import subprocess
import tempfile
from typing import Optional, BinaryIO

import boto3
import magic
from botocore.client import Config
from botocore.exceptions import ClientError
from urllib.parse import quote

from src.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MIME detection constants
# ---------------------------------------------------------------------------

# Нормализация MIME для совместимости с браузерами
_MIME_NORMALIZE = {
    "audio/x-wav": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/x-flac": "audio/flac",
    "audio/x-aac": "audio/aac",
    "audio/x-hx-aac-adts": "audio/aac",
    "video/webm": "audio/webm",
    "video/mp4": "audio/mp4",
    "application/ogg": "audio/ogg",
}

_AUDIO_EXTENSION_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
    ".opus": "audio/opus",
}

# Fix №4 — whitelist для валидации аудио-файлов
ALLOWED_AUDIO_MIMES = {
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/webm",
    "audio/mp4",
    "audio/flac",
    "audio/aac",
    "audio/opus",
    "audio/x-ms-wma",
    "audio/x-wav",       # до нормализации
    "audio/x-m4a",
    "audio/x-flac",
    "audio/x-aac",
    "audio/x-hx-aac-adts",
    "video/webm",        # WebM до нормализации
    "video/mp4",         # M4A до нормализации
    "application/ogg",   # OGG до нормализации
}


# ---------------------------------------------------------------------------
# MIME detection
# ---------------------------------------------------------------------------

def detect_audio_mime(
    data: bytes,
    filename: str | None = None,
    default: str = "application/octet-stream",
) -> str:
    """Определяет MIME-type аудио файла по содержимому (magic bytes).

    Fallback chain: libmagic → extension → default.
    Читает только первые 8192 байта — безопасно для потоков.

    Args:
        data: начало файла (минимум 8192 байт для надёжности)
        filename: имя файла (опционально, для fallback)
        default: MIME по умолчанию

    Returns:
        Нормализованный MIME-type (например "audio/mpeg", "audio/ogg")
    """
    sample = data[:8192]

    # --- 1. python-magic (libmagic) ---
    if sample:
        try:
            mime = magic.from_buffer(sample, mime=True)
            if mime and mime != "application/octet-stream":
                normalized = _MIME_NORMALIZE.get(mime, mime)
                logger.debug("MIME detected via libmagic: %s → %s", mime, normalized)
                return normalized
        except Exception as e:
            logger.warning("libmagic detection failed: %s", e)

    # --- 2. Extension-based fallback ---
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in _AUDIO_EXTENSION_MAP:
            mime = _AUDIO_EXTENSION_MAP[ext]
            logger.debug("MIME from extension '%s': %s", ext, mime)
            return mime

        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            logger.debug("MIME from mimetypes: %s", guessed)
            return guessed

    # --- 3. Default ---
    logger.warning("Could not determine MIME, using default: %s", default)
    return default


def validate_audio_mime(mime: str) -> bool:
    """Проверяет, что MIME-type является допустимым аудио-форматом."""
    return mime in ALLOWED_AUDIO_MIMES or mime.startswith("audio/")


# ---------------------------------------------------------------------------
# FFmpeg utilities (Fix №1 — замена librosa)
# ---------------------------------------------------------------------------

def _ffmpeg_convert_to_wav(input_path: str, output_path: str):
    """Конвертирует аудио в WAV 16kHz mono через ffmpeg subprocess."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,        # input file path
                "-ar", "16000",          # sample rate
                "-ac", "1",              # mono
                "-f", "wav",             # output format
                "-y",                    # overwrite
                output_path,             # output file path
            ],
            capture_output=True,
            timeout=600,                 # 10 min timeout
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")[-500:]
            raise RuntimeError(f"ffmpeg exit code {result.returncode}: {stderr}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install: apt install ffmpeg")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg conversion timed out (>600s)")


def _ffmpeg_get_duration_from_path(file_path: str) -> Optional[int]:
    """Получить длительность аудио в секундах через ffprobe из файла."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        info = json.loads(result.stdout)
        duration_str = info.get("format", {}).get("duration")
        if duration_str:
            return int(float(duration_str))
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        logger.warning("ffprobe duration detection failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# S3 Storage
# ---------------------------------------------------------------------------

class S3Storage:
    def __init__(self):
        # Обрезаем пробелы в ключах (частая причина SignatureDoesNotMatch)
        access_key = settings.S3_ACCESS_KEY.strip()
        secret_key = settings.S3_SECRET_KEY.strip()

        # Нормализуем endpoint URL (убираем trailing slash, если есть)
        endpoint_url = settings.S3_ENDPOINT_URL.rstrip('/')
        public_url = settings.S3_PUBLIC_URL.rstrip('/')

        # Логируем длину ключей
        logger.info(
            f"S3 initialization: internal_endpoint={endpoint_url}, public_endpoint={public_url}, "
            f"access_key_length={len(access_key)}, secret_key_length={len(secret_key)}, "
            f"bucket={settings.S3_BUCKET_NAME}, region={settings.S3_REGION}"
        )

        # Для MinIO требуется path-style addressing
        # Внутренний клиент (для закачки/удаления)
        internal_is_minio = (
            'minio' in endpoint_url.lower() or '/minio' in endpoint_url.lower() or '172.' in endpoint_url or '127.' in endpoint_url
        )
        internal_config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'} if internal_is_minio else {}
        )
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=settings.S3_REGION,
            config=internal_config
        )

        # Публичный клиент (для пресайн ссылок)
        public_is_minio = (
            'minio' in public_url.lower() or '/minio' in public_url.lower()
        )
        public_config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'} if public_is_minio else {}
        )
        
        self.s3_public_client = boto3.client(
            's3',
            endpoint_url=public_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=settings.S3_REGION,
            config=public_config
        )

        self.bucket_name = settings.S3_BUCKET_NAME

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def get_audio_duration_from_path(self, file_path: str) -> Optional[int]:
        """Получить длительность аудио в секундах через ffprobe."""
        return _ffmpeg_get_duration_from_path(file_path)

    # ------------------------------------------------------------------
    # Sync S3 operations (used by ARQ worker)
    # ------------------------------------------------------------------

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """Загрузить файл в S3 и вернуть (финальный_путь, content_type)."""
        try:
            # Читаем только начало для детекции MIME
            file_obj.seek(0)
            sample = file_obj.read(8192)
            file_obj.seek(0)

            if not content_type:
                content_type = detect_audio_mime(sample, filename=object_name)

            if object_name.startswith("meetings/"):
                if not validate_audio_mime(content_type):
                    logger.error(f"Rejected non-audio file: {object_name} (MIME: {content_type})")
                    raise ValueError(f"Invalid audio format: {content_type}")

            # Загружаем стримом через upload_fileobj
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs={'ContentType': content_type}
            )
            logger.info(f"File uploaded to S3: {object_name} (MIME: {content_type})")
            return object_name, content_type
        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return None, None

    def download_file(self, object_name: str) -> Optional[bytes]:
        """Скачать весь файл в память (ОСТОРОЖНО: может вызвать OOM)."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Error downloading from S3: {e}")
            return None

    def download_file_to_path(self, object_name: str, target_path: str) -> bool:
        """Скачать файл из S3 напрямую на диск."""
        try:
            logger.debug(f"Downloading from S3 to disk: {object_name} -> {target_path}")
            self.s3_client.download_file(self.bucket_name, object_name, target_path)
            return True
        except Exception as e:
            logger.error(f"Error downloading from S3 to disk: {e}")
            return False

    def delete_file(self, object_name: str) -> bool:
        """Удалить файл из S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            logger.info(f"File deleted from S3: {object_name}")
            return True
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {e}")
            return False

    def generate_presigned_url(
        self,
        object_name: str,
        expiration: int = 3600,
        as_attachment: bool = False,
        content_type: Optional[str] = None,
    ) -> Optional[str]:
        """Сгенерировать временную ссылку на файл.

        Fix №5: content_type передаётся из DB — нет head_object запроса.

        Args:
            object_name: имя объекта в S3
            expiration: время жизни ссылки в секундах
            as_attachment: если True, добавляет Content-Disposition: attachment
            content_type: MIME из DB (кеш). Если None — fallback на extension.
        """
        try:
            params = {'Bucket': self.bucket_name, 'Key': object_name}

            # Fix №5 — используем кешированный content_type из DB
            if not content_type:
                content_type = detect_audio_mime(b"", filename=object_name)

            if content_type:
                params['ResponseContentType'] = content_type

            if as_attachment:
                filename = object_name.split('/')[-1]
                params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'

            url = self.s3_public_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            logger.debug(f"Presigned URL generated (public): {object_name} (Content-Type: {content_type})")
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    def file_exists(self, object_name: str) -> bool:
        """Проверить существование файла."""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError:
            return False

    def generate_direct_url(self, object_name: str) -> Optional[str]:
        """Генерирует прямую ссылку на файл или возвращает имя дефолтной картинки.

        Если object_name содержит '/', то это путь в S3.
        Иначе — имя дефолтной картинки (обработка на фронтенде).
        """
        if not object_name:
            return None

        if '/' not in object_name:
            logger.debug(f"Using default cover image: {object_name}")
            return object_name

        base_url = settings.S3_PUBLIC_URL.rstrip('/')
        encoded_path = quote(object_name, safe='/')
        return f"{base_url}/{self.bucket_name}/{encoded_path}"

    # ------------------------------------------------------------------
    # Async wrappers (Fix №2 — для FastAPI routes)
    # ------------------------------------------------------------------

    async def async_upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """Async wrapper для upload_file — не блокирует event loop."""
        return await asyncio.to_thread(
            self.upload_file, file_obj, object_name, content_type
        )

    async def async_download_file(self, object_name: str) -> Optional[bytes]:
        """Async wrapper для download_file — не блокирует event loop."""
        return await asyncio.to_thread(self.download_file, object_name)

    async def async_generate_presigned_url(
        self,
        object_name: str,
        expiration: int = 3600,
        as_attachment: bool = False,
        content_type: Optional[str] = None,
    ) -> Optional[str]:
        """Async wrapper для generate_presigned_url — не блокирует event loop."""
        return await asyncio.to_thread(
            self.generate_presigned_url,
            object_name, expiration, as_attachment, content_type
        )

    async def async_download_file_to_path(self, object_name: str, target_path: str) -> bool:
        """Async wrapper для download_file_to_path."""
        return await asyncio.to_thread(self.download_file_to_path, object_name, target_path)

    async def async_delete_file(self, object_name: str) -> bool:
        """Async wrapper для delete_file — не блокирует event loop."""
        return await asyncio.to_thread(self.delete_file, object_name)


storage = S3Storage()
