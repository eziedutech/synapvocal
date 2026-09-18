"""Tables for voluntary contributions: who contributed, under which consent, what.

Only people who sign in and accept the consent page appear here. Nothing from the
Bridge itself is stored. Deleting a user deletes their consents and contributions
(ON DELETE CASCADE); the audio objects are removed by the API before the row goes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Consent(Base):
    """One row per acceptance. Withdrawal is recorded, never erased, until the user is deleted."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(32))
    adult_confirmed: Mapped[bool] = mapped_column(Boolean)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Contribution(Base):
    """One confirmed sentence: the recording and the text its speaker said it was."""

    __tablename__ = "contributions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    consent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consents.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    audio_key: Mapped[str] = mapped_column(String(512))
    audio_bytes: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    # What speech recognition heard, and the text the speaker confirmed.
    heard_text: Mapped[str] = mapped_column(Text)
    confirmed_text: Mapped[str] = mapped_column(Text)
    # Where the confirmed text came from: heard, suggestion, alternative or edited.
    label_source: Mapped[str] = mapped_column(String(16))
    # The speaker's answer to "Is this exactly what you said?". Only True rows are training labels.
    exact: Mapped[bool] = mapped_column(Boolean)
    stt_model: Mapped[str] = mapped_column(String(64))
    interpret_model: Mapped[str] = mapped_column(String(64), default="")
    app_version: Mapped[str] = mapped_column(String(64), default="")


@lru_cache
def get_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(url), expire_on_commit=False)
