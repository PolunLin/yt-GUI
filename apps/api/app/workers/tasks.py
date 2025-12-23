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