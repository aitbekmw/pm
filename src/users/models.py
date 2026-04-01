from sqlalchemy import String, Integer, Boolean, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from src.companies.models import Company
    from src.projects.models import Project

from src.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ad_account: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # Manager | Member | Admin | Backend Dev | Frontend Dev | Designer | QA
    admin_password: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)  # active | deactivated
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)  # TODO: make NOT NULL after backfill
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __str__(self) -> str:
        try:
            company_name = self.company.name if self.company else ""
        except Exception:
            company_name = ""
        suffix = f" [{company_name}]" if company_name else ""
        return f"{self.first_name} {self.last_name} ({self.ad_account}){suffix}"

    # Relationship
    company: Mapped["Company | None"] = relationship("Company", back_populates="users", lazy="select")
    projects: Mapped[list["Project"]] = relationship(
        "Project", secondary="project_access", back_populates="users", lazy="selectin"
    )
    push_tokens: Mapped[List["PushToken"]] = relationship(
        "PushToken", back_populates="user", lazy="select", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)


class PushToken(Base):
    __tablename__ = "push_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 'ios' | 'android'
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="push_tokens")

