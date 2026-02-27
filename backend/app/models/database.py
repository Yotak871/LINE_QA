import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings


engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, default="Untitled Analysis")
    design_image_path: Mapped[str] = mapped_column(String)
    dev_image_path: Mapped[str] = mapped_column(String)
    marked_image_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/processing/done/failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    differences: Mapped[List["Difference"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")
    share_links: Mapped[List["ShareLink"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class Difference(Base):
    __tablename__ = "differences"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"))
    category: Mapped[str] = mapped_column(String)   # typography/color/spacing/layout/missing
    severity: Mapped[str] = mapped_column(String)   # critical/major/minor
    description: Mapped[str] = mapped_column(Text)
    design_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dev_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bbox_x: Mapped[int] = mapped_column(Integer, default=0)
    bbox_y: Mapped[int] = mapped_column(Integer, default=0)
    bbox_w: Mapped[int] = mapped_column(Integer, default=0)
    bbox_h: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="issue")  # issue/approved/ignored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    analysis: Mapped["Analysis"] = relationship(back_populates="differences")


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"))
    short_id: Mapped[str] = mapped_column(String, unique=True, default=lambda: str(uuid.uuid4())[:8])
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    analysis: Mapped["Analysis"] = relationship(back_populates="share_links")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
