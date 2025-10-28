import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO
import io
from datetime import datetime, timedelta
import librosa
import soundfile as sf

from src.core.config import settings


class S3Storage:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version='s3v4')
        )
        self.bucket_name = settings.S3_BUCKET_NAME

    def upload_file(self, file_obj: BinaryIO, object_name: str, content_type: str = "audio/mpeg") -> bool:
        """Загрузить файл в S3"""
        try:
            # Если это аудиофайл (начинается с meetings/), конвертируем в WAV
            if object_name.startswith("meetings/"):
                file_obj.seek(0)
                audio_bytes = file_obj.read()
                
                try:
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
                except Exception as e:
                    print(f"Предупреждение: не удалось конвертировать аудио в WAV, загружаем оригинальный файл: {e}")
                    file_obj.seek(0)
            
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs={'ContentType': content_type}
            )
            return True
        except ClientError as e:
            print(f"Error uploading file: {e}")
            return False

    def download_file(self, object_name: str) -> Optional[bytes]:
        """Скачать файл из S3"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
            return response['Body'].read()
        except ClientError as e:
            print(f"Error downloading file: {e}")
            return None

    def delete_file(self, object_name: str) -> bool:
        """Удалить файл из S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError as e:
            print(f"Error deleting file: {e}")
            return False

    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        """Сгенерировать временную ссылку на файл"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_name},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return None

    def file_exists(self, object_name: str) -> bool:
        """Проверить существование файла"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError:
            return False


storage = S3Storage()

