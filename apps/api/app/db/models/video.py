from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.db.base import Base


class Video(Base):
    __tablename__ = "videos"

    video_id: Mapped[str] = mapped_column(String, primary_key=True)
    webpage_url: Mapped[str] = mapped_column(Text)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploader: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_date: Mapped[str | None] = mapped_column(String(16), nullable=True)

    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_short: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
        
    last_download_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)