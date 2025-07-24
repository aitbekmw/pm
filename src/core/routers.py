from fastapi import APIRouter
from src.user.router import router as user_router
from src.project.router import router as project_router
from src.meeting.router import router as meeting_router

api_router = APIRouter()
api_router.include_router(user_router)
api_router.include_router(project_router)
api_router.include_router(meeting_router)