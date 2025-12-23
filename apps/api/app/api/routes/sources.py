import re
from typing import Optional
from uuid import uuid4
from datetime import datetime

import yt_dlp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.db.session import get_db
from apps.api.app.db.models.video import Video
from apps.api.app.db.models.scan_job import ScanJob
from apps.api.app.workers.queue import scan_queue
from apps.api.app.workers.tasks import scan_task
import os
from datetime import datetime
from uuid import uuid4
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
router = APIRouter()


class ScanChannelReq(BaseModel):
    channel: str  # handle or full url
    include_shorts: bool = True
    include_videos: bool = True
    include_streams: bool = False
    max_items: int = 50


def normalize_channel_to_handle(channel: str) -> str:
    s = channel.strip()
    if not s:
        raise HTTPException(400, "channel is required")

    # Accept:
    # - InnahBee
    # - @InnahBee
    # - https://www.youtube.com/@InnahBee
    m = re.search(r"youtube\.com/@([^/?#]+)", s)
    if m:
        return m.group(1)

    s = s.lstrip("@")
    # Basic sanity
    if "/" in s or " " in s:
        raise HTTPException(400, "channel must be a handle like InnahBee or @InnahBee or youtube.com/@InnahBee")
    return s


def fetch_flat_entries(list_url: str, max_items: int) -> list[dict]:
    max_items = max(1, int(max_items))

    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "playlistend": max_items,
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            entries = data.get("entries", []) if data else []
            return entries[:max_items]  # ✅ 強制 max 生效
    except Exception:
        return []   # ✅ 出錯就當這個分頁掃不到，不要 500


def fetch_detail(video_url: str):
    opts = {
        "quiet": True,
        "skip_download": True,
        "ignoreerrors": True,
        "retries": 3,
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            return ydl.extract_info(video_url, download=False)
        except Exception:
            return None


def upsert_video(db: Session, info: dict):
    vid = info.get("id")
    if not vid:
        return

    # 判斷 shorts：最簡單先用 duration < 61
    duration = info.get("duration")
    is_short = 1 if (duration is not None and duration < 61) else 0

    v = db.get(Video, vid)
    if not v:
        v = Video(video_id=vid)
        db.add(v)

    v.webpage_url = info.get("webpage_url")
    v.title = info.get("title")
    v.duration = duration
    v.view_count = info.get("view_count")
    v.upload_date = info.get("upload_date")
    v.uploader = info.get("uploader")
    v.is_short = is_short


from pydantic import BaseModel, Field

class ScanReq(BaseModel):
    channel: str
    include_shorts: bool = True
    include_videos: bool = True
    include_streams: bool = False
    max_items: int = Field(default=30, ge=0)  # ✅ 允許 0


SCAN_CAP = int(os.getenv("SCAN_CAP", "5000"))  # 你可自行調整

@router.post("/scan")
def create_scan(payload: ScanReq, db: Session = Depends(get_db)):
    ch = payload.channel.strip()
    if not ch:
        raise HTTPException(400, "channel is required")

    requested = int(payload.max_items or 0)

    # 0 代表全抓（但最多 SCAN_CAP）
    if requested <= 0:
        effective = SCAN_CAP
    else:
        effective = min(requested, SCAN_CAP)

    scan_id = str(uuid4())
    job = ScanJob(
        scan_id=scan_id,
        channel=ch,
        include_shorts=payload.include_shorts,
        include_videos=payload.include_videos,
        include_streams=payload.include_streams,
        max_items=effective,
        status="queued",
        progress=0,
        counts={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    scan_queue.enqueue(scan_task, scan_id, job_id=scan_id)

    # ✅ 直接把有效值回給前端/你自己 debug
    return {
        "scan_id": scan_id,
        "status": "queued",
        "requested_max_items": requested,
        "effective_max_items": effective,
        "cap": SCAN_CAP,
    }
@router.get("/scan/{scan_id}")
def get_scan(scan_id: str, db: Session = Depends(get_db)):
    job = db.get(ScanJob, scan_id)
    if not job:
        raise HTTPException(404, "scan job not found")
    return {
        "scan_id": job.scan_id,
        "channel": job.channel,
        "status": job.status,
        "progress": job.progress,
        "counts": job.counts,
        "unique_videos": job.unique_videos,
        "inserted": job.inserted,
        "updated": job.updated,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }