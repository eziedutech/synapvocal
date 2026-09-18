"""Voluntary contributions: sign-in record, consent, recordings and their deletion.

Only frontrouter calls these routes. It proves itself with the shared internal token
and names the signed-in user in X-User-Id after checking its own session cookie; the
browser never reaches backpy. Every route refuses to work until contributions are
configured, so a deployment without a database behaves exactly as before.
"""

from __future__ import annotations

import hmac
import io
import logging
import uuid
import wave
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contrib.db import Consent, Contribution, User, now, session_factory
from app.contrib.storage import get_storage
from app.settings import Settings, get_settings

log = logging.getLogger("synapvocal.contrib")

router = APIRouter(prefix="/api")

# The consent text lives on the frontrouter consent page. Its date is the version, and a
# consent is only valid for the text currently shown: change both together.
CONSENT_VERSION = "2026-09-18"

MAX_AUDIO_BYTES = 2_500_000  # about 78 s of 16 kHz mono 16-bit
MIN_DURATION_MS = 300
MAX_DURATION_MS = 60_000


def require_configured(settings: Settings = Depends(get_settings)) -> Settings:
    if not settings.contributions_configured:
        raise HTTPException(status_code=503, detail="Contributions are not configured")
    return settings


def require_internal(
    settings: Settings = Depends(require_configured),
    x_internal_token: Annotated[str, Header()] = "",
) -> Settings:
    if not hmac.compare_digest(x_internal_token.encode(), settings.internal_api_token.encode()):
        raise HTTPException(status_code=401, detail="Unknown caller")
    return settings


async def get_db(settings: Settings = Depends(require_internal)) -> AsyncIterator[AsyncSession]:
    async with session_factory(settings.database_url)() as session:
        yield session


async def current_user(
    x_user_id: Annotated[str, Header()] = "",
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Not signed in") from exc
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


async def active_consent(db: AsyncSession, user: User) -> Consent | None:
    result = await db.execute(
        select(Consent)
        .where(Consent.user_id == user.id, Consent.withdrawn_at.is_(None), Consent.version == CONSENT_VERSION)
        .order_by(Consent.accepted_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


class ConsentView(BaseModel):
    version: str
    accepted_at: datetime


class Me(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    consent: ConsentView | None
    consent_version: str = CONSENT_VERSION
    contributions: int


async def describe(db: AsyncSession, user: User) -> Me:
    consent = await active_consent(db, user)
    count = await db.scalar(select(func.count()).select_from(Contribution).where(Contribution.user_id == user.id))
    return Me(
        id=user.id,
        email=user.email,
        name=user.name,
        consent=ConsentView(version=consent.version, accepted_at=consent.accepted_at) if consent else None,
        contributions=count or 0,
    )


class SyncRequest(BaseModel):
    google_sub: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(default="", max_length=255)


@router.post("/users/sync", response_model=Me)
async def sync_user(body: SyncRequest, db: AsyncSession = Depends(get_db)) -> Me:
    """Called after Google sign-in. Creates the user on first sign-in, refreshes the rest."""
    user = (await db.execute(select(User).where(User.google_sub == body.google_sub))).scalar_one_or_none()
    if user is None:
        user = User(google_sub=body.google_sub, email=body.email, name=body.name)
        db.add(user)
        log.info("new contributor account")
    else:
        user.email, user.name, user.last_login_at = body.email, body.name, now()
    await db.commit()
    return await describe(db, user)


@router.get("/me", response_model=Me)
async def get_me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> Me:
    return await describe(db, user)


class ConsentRequest(BaseModel):
    version: str
    adult_confirmed: bool
    agreed: bool


@router.post("/me/consent", response_model=Me)
async def give_consent(body: ConsentRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> Me:
    if body.version != CONSENT_VERSION:
        raise HTTPException(status_code=409, detail="The consent text has changed. Reload the page and read it again.")
    if not (body.adult_confirmed and body.agreed):
        raise HTTPException(status_code=422, detail="Both confirmations are needed to contribute")
    if await active_consent(db, user) is None:
        db.add(Consent(user_id=user.id, version=CONSENT_VERSION, adult_confirmed=True))
        await db.commit()
        log.info("consent given, version %s", CONSENT_VERSION)
    return await describe(db, user)


async def delete_contributions(db: AsyncSession, settings: Settings, user: User) -> int:
    rows = (await db.execute(select(Contribution).where(Contribution.user_id == user.id))).scalars().all()
    storage = get_storage(settings)
    for row in rows:
        await storage.delete(row.audio_key)
        await db.delete(row)
    return len(rows)


class WithdrawRequest(BaseModel):
    delete_contributions: bool


@router.post("/me/consent/withdraw", response_model=Me)
async def withdraw_consent(
    body: WithdrawRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(require_internal),
) -> Me:
    consents = (await db.execute(select(Consent).where(Consent.user_id == user.id, Consent.withdrawn_at.is_(None)))).scalars().all()
    for consent in consents:
        consent.withdrawn_at = now()
    deleted = await delete_contributions(db, settings, user) if body.delete_contributions else 0
    await db.commit()
    log.info("consent withdrawn, %d contributions deleted", deleted)
    return await describe(db, user)


@router.delete("/me", status_code=204)
async def delete_me(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(require_internal),
) -> None:
    """Deletes the recordings, then the account; consents and rows go with it."""
    deleted = await delete_contributions(db, settings, user)
    await db.delete(user)
    await db.commit()
    log.info("account deleted with %d contributions", deleted)


class ContributionMeta(BaseModel):
    heard_text: str = Field(min_length=1, max_length=2000)
    confirmed_text: str = Field(min_length=1, max_length=2000)
    label_source: Literal["heard", "suggestion", "alternative", "edited"]
    exact: bool
    stt_model: str = Field(max_length=64)
    interpret_model: str = Field(default="", max_length=64)
    app_version: str = Field(default="", max_length=64)


class ContributionView(BaseModel):
    id: uuid.UUID
    created_at: datetime
    confirmed_text: str
    exact: bool
    duration_ms: int


def check_wav(data: bytes) -> int:
    """Returns the duration in ms of a 16 kHz mono 16-bit WAV, or raises 422."""
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too long")
    try:
        with wave.open(io.BytesIO(data)) as wav:
            shape = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
            frames = wav.getnframes()
    except (wave.Error, EOFError) as exc:
        raise HTTPException(status_code=422, detail="Recording is not a WAV file") from exc
    if shape != (16000, 1, 2):
        raise HTTPException(status_code=422, detail="Recording must be 16 kHz mono 16-bit")
    duration_ms = round(frames / 16)
    if not MIN_DURATION_MS <= duration_ms <= MAX_DURATION_MS:
        raise HTTPException(status_code=422, detail="Recording length is out of range")
    return duration_ms


@router.post("/contributions", response_model=ContributionView, status_code=201)
async def add_contribution(
    audio: UploadFile = File(...),
    meta: str = Form(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(require_internal),
) -> ContributionView:
    consent = await active_consent(db, user)
    if consent is None:
        raise HTTPException(status_code=403, detail="Consent is needed before contributing")
    try:
        info = ContributionMeta.model_validate_json(meta)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Contribution details are incomplete") from exc
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    duration_ms = check_wav(data)

    contribution_id = uuid.uuid4()
    key = f"{user.id}/{contribution_id}.wav"
    await get_storage(settings).put(key, data, "audio/wav")
    row = Contribution(
        id=contribution_id,
        user_id=user.id,
        consent_id=consent.id,
        audio_key=key,
        audio_bytes=len(data),
        duration_ms=duration_ms,
        **info.model_dump(),
    )
    db.add(row)
    try:
        await db.commit()
    except Exception:
        await get_storage(settings).delete(key)  # never leave an object without its row
        raise
    log.info("contribution saved: %d ms, source %s, exact %s", duration_ms, info.label_source, info.exact)
    return ContributionView(id=row.id, created_at=row.created_at, confirmed_text=row.confirmed_text, exact=row.exact, duration_ms=duration_ms)


@router.get("/contributions", response_model=list[ContributionView])
async def list_contributions(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[ContributionView]:
    rows = (
        await db.execute(select(Contribution).where(Contribution.user_id == user.id).order_by(Contribution.created_at.desc()))
    ).scalars()
    return [ContributionView(id=r.id, created_at=r.created_at, confirmed_text=r.confirmed_text, exact=r.exact, duration_ms=r.duration_ms) for r in rows]


@router.get("/contributions/{contribution_id}/audio")
async def contribution_audio(
    contribution_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(require_internal),
) -> Response:
    """The recording, only for the person who contributed it, so they can hear what they gave."""
    row = await db.get(Contribution, contribution_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contribution not found")
    data = await get_storage(settings).get(row.audio_key)
    return Response(content=data, media_type="audio/wav", headers={"Cache-Control": "private, no-store"})


@router.delete("/contributions/{contribution_id}", status_code=204)
async def delete_contribution(
    contribution_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(require_internal),
) -> None:
    row = await db.get(Contribution, contribution_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contribution not found")
    await get_storage(settings).delete(row.audio_key)
    await db.delete(row)
    await db.commit()
