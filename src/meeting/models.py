from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

class MeetingType(Base):
    __tablename__ = "meeting_type"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    started_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    meeting_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("meeting_type.id"))
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="meetings")
    started_by_user: Mapped["User"] = relationship("User", back_populates="meetings_started")

    # 🔻 Закомментированы до добавления соответствующих моделей:
    audio_file: Mapped["AudioFile"] = relationship("AudioFile", uselist=False, back_populates="meeting")
    # transcript: Mapped["Transcript"] = relationship("Transcript", uselist=False, back_populates="meeting")
    # summary: Mapped["Summary"] = relationship("Summary", uselist=False, back_populates="meeting")

    

class AudioFile(Base):
    __tablename__ = "audio_file"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id"))
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="audio_file")




'''
class Transcript(Base):
    __tablename__ = "transcript"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="transcript")

class Summary(Base):
    __tablename__ = "summary"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id"))
    summary_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="summary") 

'''
