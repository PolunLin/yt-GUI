from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.db.base import Base


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)  # 例如 channel handle 或自訂 id
    source_type: Mapped[str] = mapped_column(String(32), default="youtube_channel")  # 可擴充
    url: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)