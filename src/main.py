import logging

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from src.database.init_db import create_db_and_tables
from src.core.config import settings
from src.core.setup_app import create_app
from src.core.error_handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from src.core.routers import api_router


from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import boto3
from botocore.exceptions import BotoCoreError, ClientError


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s", level=logging.DEBUG
)

app = create_app()
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {"message": "hello"}


from sqlalchemy import text

@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()

@app.get("/db-check")
async def db_check():
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "success", "message": "Database connection successful"}
    except SQLAlchemyError as e:
        return {"status": "error", "message": str(e)}

@app.get("/s3-check")
async def s3_check():
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.ENDPOINT_URL,  # make sure to include this for MinIO!
            aws_access_key_id=settings.ACCESS_KEY_ID,
            aws_secret_access_key=settings.SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION_NAME,
        )
        s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        return {"status": "success", "message": "S3 connection successful"}
    except (BotoCoreError, ClientError) as e:
        return {"status": "error", "message": str(e)}
    


app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
