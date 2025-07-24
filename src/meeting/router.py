from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from .models import Meeting
from .schemas import MeetingRead, MeetingCreate, MeetingBase
from src.database import get_db
from sqlalchemy.future import select

router = APIRouter(prefix="/meetings", tags=["meetings"])

@router.get("/", response_model=List[MeetingRead])
async def list_meetings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Meeting))
    meetings = result.scalars().all()
    return meetings

@router.get("/{id}", response_model=MeetingRead)
async def get_meeting(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Meeting).where(Meeting.id == id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting

@router.post("/", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting(meeting_in: MeetingCreate, db: AsyncSession = Depends(get_db)):
    meeting = Meeting(**meeting_in.dict())
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    return meeting

@router.patch("/{id}", response_model=MeetingRead)
async def update_meeting(id: int, meeting_update: MeetingBase, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Meeting).where(Meeting.id == id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    for field, value in meeting_update.dict(exclude_unset=True).items():
        setattr(meeting, field, value)
    await db.commit()
    await db.refresh(meeting)
    return meeting

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Meeting).where(Meeting.id == id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    await db.delete(meeting)
    await db.commit()
    return None 



from src.meeting.utils import upload_to_s3, delete_from_s3, generate_presigned_url

@router.post("/{id}/upload-audio")
async def upload_meeting_audio(id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Meeting).where(Meeting.id == id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    key = f"meetings/{id}/{file.filename}"
    url = await upload_to_s3(file, key)
    
    # Optionally: Save AudioFile model here
    return {"s3_url": url, "s3_key": key}

@router.delete("/{id}/delete-audio")
async def delete_meeting_audio(id: int, key: str):
    # You could validate that meeting exists first if needed
    delete_from_s3(key)
    return {"message": f"Deleted audio file: {key}"}

@router.get("/{id}/audio-url")
async def get_presigned_audio_url(id: int, key: str, expires_in: int = 3600):
    url = generate_presigned_url(key, expires_in)
    return {"presigned_url": url}
