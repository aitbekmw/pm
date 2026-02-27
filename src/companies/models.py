from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from src.db.base import Base

if TYPE_CHECKING:
    from src.users.models import User
    from src.projects.models import Project
    from src.meetings.models import Meeting


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="company")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="company")
    meetings: Mapped[list["Meeting"]] = relationship("Meeting", back_populates="company")
