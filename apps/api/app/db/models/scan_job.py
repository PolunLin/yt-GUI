from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.db.base import Base

class ScanJob(Base):
    __tablename__ = "scan_jobs"

    scan_id: Mapped[str] = mapped_column(String, primary_key=True)
    channel: Mapped[str] = mapped_column(String, nullable=False)

    include_shorts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_videos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_streams: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_items: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"shorts":5,"videos":5,"streams":0}
    unique_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_message: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)