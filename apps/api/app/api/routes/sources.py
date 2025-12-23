import re
from typing import Optional

import yt_dlp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.db.session import get_db
from apps.api.app.db.models.video import Video

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
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(list_url, download=False)
        entries = data.get("entries", []) if data else []
        return entries[:max_items]   # ✅ 強制截斷（最重要）


def fetch_detail(video_url: str) -> Optional[dict]:
    opts = {
        "quiet": True,
        "skip_download": True,
        "ignoreerrors": True,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        return info


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


@router.post("/scan")
def scan_channel(payload: ScanChannelReq, db: Session = Depends(get_db)):
    handle = normalize_channel_to_handle(payload.channel)
    base = f"https://www.youtube.com/@{handle}"

    targets: list[tuple[str, str]] = []
    if payload.include_shorts:
        targets.append(("shorts", base + "/shorts"))
    if payload.include_videos:
        targets.append(("videos", base + "/videos"))
    if payload.include_streams:
        targets.append(("streams", base + "/streams"))

    if not targets:
        raise HTTPException(400, "select at least one of include_shorts/include_videos/include_streams")

    inserted = 0
    updated = 0
    seen_ids: set[str] = set()

    for label, url in targets:
        entries = fetch_flat_entries(url, payload.max_items)
        for e in entries:
            vid = e.get("id")
            vurl = e.get("url") or e.get("webpage_url")
            if not vid or not vurl or vid in seen_ids:
                continue
            seen_ids.add(vid)

            info = fetch_detail(vurl)
            if not info or not info.get("id"):
                continue

            existed = db.get(Video, info["id"]) is not None
            upsert_video(db, info)
            if existed:
                updated += 1
            else:
                inserted += 1

    db.commit()

    return {
        "channel": handle,
        "scanned": len(seen_ids),
        "inserted": inserted,
        "updated": updated,
    }