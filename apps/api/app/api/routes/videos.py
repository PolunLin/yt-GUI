from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.db.session import get_db
from apps.api.app.db.models.video import Video
from apps.api.app.integrations.ytdlp_client import extract_info

router = APIRouter()

class AddByUrlReq(BaseModel):
    url: str

@router.post("/by_url")
def add_by_url(payload: AddByUrlReq, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not url:
        raise HTTPException(400, "url is required")

    try:
        info = extract_info(url)
    except Exception as e:
        raise HTTPException(400, f"extract failed: {e}")

    vid = info.get("id")
    if not vid:
        raise HTTPException(400, "yt-dlp did not return video id")

    duration = info.get("duration")
    is_short = 1 if (duration is not None and duration <= 60) else 0

    v = db.get(Video, vid)
    if not v:
        v = Video(
            video_id=vid,
            webpage_url=info.get("webpage_url") or url,
            title=info.get("title"),
            duration=duration,
            view_count=info.get("view_count"),
            upload_date=info.get("upload_date"),
            uploader=info.get("uploader"),
            is_short=is_short,
        )
        db.add(v)
    else:
        # 更新資料
        v.webpage_url = info.get("webpage_url") or v.webpage_url
        v.title = info.get("title") or v.title
        v.duration = duration if duration is not None else v.duration
        v.view_count = info.get("view_count") if info.get("view_count") is not None else v.view_count
        v.upload_date = info.get("upload_date") or v.upload_date
        v.uploader = info.get("uploader") or v.uploader
        v.is_short = is_short

    db.commit()
    return {"ok": True, "video_id": vid}

@router.get("")
def list_videos(
    q: str | None = Query(default=None),
    is_short: int | None = Query(default=None),
    min_views: int | None = Query(default=None),
    max_duration: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Video).order_by(Video.created_at.desc())

    if q:
        stmt = stmt.where(Video.title.contains(q))
    if is_short is not None:
        stmt = stmt.where(Video.is_short == is_short)
    if min_views is not None:
        stmt = stmt.where(Video.view_count.is_not(None)).where(Video.view_count >= min_views)
    if max_duration is not None:
        stmt = stmt.where(Video.duration.is_not(None)).where(Video.duration <= max_duration)

    rows = db.execute(stmt).scalars().all()
    return [
        {
            "video_id": v.video_id,
            "webpage_url": v.webpage_url,
            "title": v.title,
            "duration": v.duration,
            "view_count": v.view_count,
            "upload_date": v.upload_date,
            "uploader": v.uploader,
            "is_short": v.is_short,
            "created_at": v.created_at,
        }
        for v in rows
    ]