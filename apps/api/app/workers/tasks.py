import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from apps.api.app.db.session import SessionLocal
from apps.api.app.db.models.video import Video
from apps.api.app.db.models.download_job import DownloadJob
from apps.api.app.integrations.ytdlp_client import download_video

log = logging.getLogger("worker")

VIDEO_OUTDIR = os.getenv("VIDEO_OUTDIR", "/app/storage/videos")
MAX_HEIGHT = int(os.getenv("MAX_HEIGHT", "1080"))


def download_task(job_id: str, video_id: str):
    db: Session = SessionLocal()
    try:
        job = db.get(DownloadJob, job_id)
        if not job:
            raise RuntimeError(f"download job not found: {job_id}")

        v = db.get(Video, video_id)
        if not v:
            raise RuntimeError(f"video not found: {video_id}")

        log.info("download start job=%s video=%s", job_id, video_id)

        # 開始
        job.status = "running"
        job.progress = 5
        job.started_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()

        # 若已存在檔案（多保險一次）
        if job.output_path and os.path.exists(job.output_path):
            job.status = "success"
            job.progress = 100
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()

            # Mark video as downloaded (requires columns on Video model)
            if hasattr(v, "last_download_job_id"):
                v.last_download_job_id = job.job_id
            if hasattr(v, "downloaded_at"):
                v.downloaded_at = datetime.utcnow()

            db.commit()
            log.info("download already-present job=%s out=%s", job_id, job.output_path)
            return {"output_path": job.output_path}

        out = download_video(
            url=v.webpage_url,
            base_outdir=VIDEO_OUTDIR,
            video_id=video_id,
            uploader=v.uploader,
            max_height=MAX_HEIGHT,
        )

        job.status = "success"
        job.progress = 100
        job.output_path = out
        job.error_message = None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()

        # Mark video as downloaded (requires columns on Video model)
        if hasattr(v, "last_download_job_id"):
            v.last_download_job_id = job.job_id
        if hasattr(v, "downloaded_at"):
            v.downloaded_at = datetime.utcnow()

        db.commit()
        log.info("download success job=%s out=%s", job_id, out)
        return {"output_path": out}

    except Exception as e:
        job = db.get(DownloadJob, job_id)
        if job:
            job.status = "failed"
            job.progress = 0
            job.error_message = str(e)
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
        log.exception("download failed job=%s video=%s", job_id, video_id)
        raise
    finally:
        db.close()
        
        
import re
from datetime import datetime
import yt_dlp

from apps.api.app.db.session import SessionLocal
from apps.api.app.db.models.scan_job import ScanJob
from apps.api.app.db.models.video import Video

def _normalize_handle(channel: str) -> str:
    s = channel.strip()
    m = re.search(r"youtube\.com/@([^/?#]+)", s)
    if m:
        return m.group(1)
    return s.lstrip("@")

def _fetch_flat(list_url: str, max_items: int) -> list[dict]:
    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "playlistend": max_items,
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(list_url, download=False)
        entries = data.get("entries", []) if data else []
        return entries[:max_items]  # ✅ 強制 max 生效

def _fetch_detail(url: str) -> dict | None:
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
            return ydl.extract_info(url, download=False)
        except Exception:
            return None

def _upsert_video(db, info: dict) -> bool:
    vid = info.get("id")
    if not vid:
        return False

    existed = db.get(Video, vid) is not None
    v = db.get(Video, vid) or Video(video_id=vid)
    db.add(v)

    duration = info.get("duration")
    v.webpage_url = info.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    v.title = info.get("title")
    v.duration = duration
    v.view_count = info.get("view_count")
    v.upload_date = info.get("upload_date")
    v.uploader = info.get("uploader")
    v.is_short = 1 if (duration is not None and duration < 61) else 0

    return existed

def scan_task(scan_id: str):
    db = SessionLocal()
    try:
        job = db.get(ScanJob, scan_id)
        if not job:
            return

        job.status = "running"
        job.progress = 1
        job.started_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()

        handle = _normalize_handle(job.channel)
        base = f"https://www.youtube.com/@{handle}"

        targets: list[tuple[str, str]] = []
        if job.include_shorts: targets.append(("shorts", base + "/shorts"))
        if job.include_videos: targets.append(("videos", base + "/videos"))
        if job.include_streams: targets.append(("streams", base + "/streams"))

        flat_map = {}
        counts = {"shorts": 0, "videos": 0, "streams": 0}
        total = 0

        for label, url in targets:
            entries = _fetch_flat(url, job.max_items)
            flat_map[label] = entries
            counts[label] = len(entries)
            total += len(entries)

        job.counts = counts
        job.updated_at = datetime.utcnow()
        db.commit()

        seen = set()
        inserted = updated = 0
        done = 0

        for label, _ in targets:
            entries = flat_map[label]
            for e in entries:
                vid = e.get("id")
                vurl = e.get("url") or e.get("webpage_url")

                if not vid:
                    done += 1
                    continue

                if not vurl or not str(vurl).startswith("http"):
                    vurl = f"https://www.youtube.com/watch?v={vid}"

                if vid in seen:
                    done += 1
                    continue
                seen.add(vid)

                info = _fetch_detail(vurl)
                if info and info.get("id"):
                    existed = _upsert_video(db, info)
                    if existed:
                        updated += 1
                    else:
                        inserted += 1
                    db.commit()

                done += 1
                if total > 0:
                    job.progress = min(99, 10 + int(done / total * 89))
                job.unique_videos = len(seen)
                job.inserted = inserted
                job.updated = updated
                job.updated_at = datetime.utcnow()
                db.commit()

        job.status = "success"
        job.progress = 100
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        job = db.get(ScanJob, scan_id)
        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()