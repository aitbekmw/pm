from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.logging import setup_logging
from src.users.routes import router as users_router


setup_logging()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(users_router, prefix=settings.api_prefix)

@app.get("/")
async def root():
    return {"message": "API for meeting"}

@app.get("/health")
async def health():
    return {"status": "ok"}
