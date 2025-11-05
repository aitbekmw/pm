import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO
import io
from datetime import datetime, timedelta
import librosa
import soundfile as sf
import logging

from src.core.config import settings

logger = logging.getLogger(__name__)


class S3Storage:
    def __init__(self):
        # Обрезаем пробелы в ключах (частая причина SignatureDoesNotMatch)
        access_key = settings.S3_ACCESS_KEY.strip()
        secret_key = settings.S3_SECRET_KEY.strip()
        
        # Логируем длину ключей (без самих значений для безопасности)
        logger.info(f"S3 initialization: endpoint={settings.S3_ENDPOINT_URL}, "
                   f"access_key_length={len(access_key)}, secret_key_length={len(secret_key)}, "
                   f"bucket={settings.S3_BUCKET_NAME}, region={settings.S3_REGION}")
        
        # Для MinIO требуется path-style addressing
        is_minio = 'minio' in settings.S3_ENDPOINT_URL.lower() or settings.S3_ENDPOINT_URL.startswith('http://')
        
        # Настройка конфигурации для MinIO
        if is_minio:
            s3_config = Config(
                signature_version='s3v4',
                s3={
                    'addressing_style': 'path'
                }
            )
        else:
            s3_config = Config(signature_version='s3v4')
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=settings.S3_REGION,
            config=s3_config
        )
        self.bucket_name = settings.S3_BUCKET_NAME

    def get_audio_duration(self, audio_bytes: bytes) -> Optional[int]:
        """Получить длительность аудио в секундах"""
        try:
            audio_data, sr = librosa.load(io.BytesIO(audio_bytes), sr=None, mono=True)
            duration_seconds = int(librosa.get_duration(y=audio_data, sr=sr))
            logger.info(f"Audio duration calculated: {duration_seconds} seconds")
            return duration_seconds
        except Exception as e:
            logger.error(f"Error calculating audio duration: {e}")
            return None

    def upload_file(self, file_obj: BinaryIO, object_name: str, content_type: str = "audio/mpeg") -> Optional[str]:
        """Загрузить файл в S3 и вернуть финальный путь файла"""
        try:
            # Если это аудиофайл (начинается с meetings/), конвертируем в WAV
            if object_name.startswith("meetings/"):
                file_obj.seek(0)
                audio_bytes = file_obj.read()
                
                # Проверяем размер файла
                if len(audio_bytes) == 0:
                    logger.warning(f"Audio file is empty, skipping conversion: {object_name}")
                    file_obj.seek(0)
                elif len(audio_bytes) > 100 * 1024 * 1024:  # 100MB limit
                    logger.warning(f"Audio file too large ({len(audio_bytes)} bytes), skipping conversion: {object_name}")
                    file_obj.seek(0)
                else:
                    try:
                        logger.info(f"Converting audio to WAV: {object_name} (size: {len(audio_bytes)} bytes)")
                        # Загружаем аудио
                        audio_data, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
                        
                        # Сохраняем в WAV формат
                        wav_buffer = io.BytesIO()
                        sf.write(wav_buffer, audio_data, sr, format='WAV')
                        wav_buffer.seek(0)
                        file_obj = wav_buffer
                        content_type = "audio/wav"
                        
                        # Обновляем имя файла на .wav
                        object_name = object_name.rsplit('.', 1)[0] + '.wav'
                        logger.info(f"Audio conversion successful: {object_name}")
                    except Exception as e:
                        logger.warning(f"Failed to convert audio to WAV, uploading original file: {e}")
                        file_obj = io.BytesIO(audio_bytes)
                        file_obj.seek(0)
            
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs={'ContentType': content_type}
            )
            logger.info(f"File uploaded successfully to S3: {object_name}")
            return object_name
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(
                f"Error uploading file to S3: {error_code} - {error_message}. "
                f"Bucket: {self.bucket_name}, Key: {object_name}"
            )
            return None

    def download_file(self, object_name: str) -> Optional[bytes]:
        """Скачать файл из S3"""
        try:
            logger.debug(f"Downloading file from S3: bucket={self.bucket_name}, key={object_name}")
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
            data = response['Body'].read()
            logger.info(f"Successfully downloaded file from S3: {object_name}, size={len(data)} bytes")
            return data
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(
                f"Error downloading file from S3: {error_code} - {error_message}. "
                f"Bucket: {self.bucket_name}, Key: {object_name}, "
                f"Endpoint: {settings.S3_ENDPOINT_URL}"
            )
            # Дополнительная информация для диагностики SignatureDoesNotMatch
            if error_code == 'SignatureDoesNotMatch':
                logger.error(
                    "SignatureDoesNotMatch - возможные причины:\n"
                    "- Пробелы в начале/конце S3_ACCESS_KEY или S3_SECRET_KEY (должны быть обрезаны автоматически)\n"
                    "- Неправильные значения ключей\n"
                    "- Проблемы с кодировкой ключей\n"
                    "- Неправильный endpoint URL"
                )
            return None

    def delete_file(self, object_name: str) -> bool:
        """Удалить файл из S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            logger.info(f"File deleted from S3: {object_name}")
            return True
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {e}")
            return False

    def generate_presigned_url(self, object_name: str, expiration: int = 3600, as_attachment: bool = False) -> Optional[str]:
        """Сгенерировать временную ссылку на файл
        
        Args:
            object_name: имя объекта в S3
            expiration: время жизни ссылки в секундах
            as_attachment: если True, добавляет Content-Disposition: attachment
        """
        try:
            params = {'Bucket': self.bucket_name, 'Key': object_name}
            
            # Если нужно скачивать как attachment, добавляем параметр
            if as_attachment:
                # Получаем имя файла из пути
                filename = object_name.split('/')[-1]
                params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            logger.debug(f"Presigned URL generated for: {object_name}")
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    def file_exists(self, object_name: str) -> bool:
        """Проверить существование файла"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError:
            return False


storage = S3Storage()

