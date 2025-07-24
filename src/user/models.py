from sqlalchemy import (
    Integer,
    String,
    Text,
    ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

class Role(Base):
    __tablename__ = "role"
    role_name: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    users: Mapped[list["User"]] = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    ad_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String, ForeignKey("role.role_name"))

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    project_memberships: Mapped[list["ProjectMembership"]] = relationship("ProjectMembership", back_populates="user")
    meetings_started: Mapped[list["Meeting"]] = relationship("Meeting", back_populates="started_by_user") 