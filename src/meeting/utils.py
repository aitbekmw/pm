import boto3
from fastapi import UploadFile
from src.core.config import settings


s3 = boto3.client(
    "s3",
    endpoint_url=settings.ENDPOINT_URL,
    aws_access_key_id=settings.ACCESS_KEY_ID,
    aws_secret_access_key=settings.SECRET_ACCESS_KEY,
    region_name=settings.S3_REGION_NAME,
)

async def upload_to_s3(file: UploadFile, key: str) -> str:
    content = await file.read()
    s3.put_object(Bucket=settings.S3_BUCKET_NAME, Key=key, Body=content)
    return f"https://{settings.S3_BUCKET_NAME}.s3.amazonaws.com/{key}"

def delete_from_s3(key: str):
    s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)

def generate_presigned_url(key: str, expires_in: int = 3600):
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
