import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from uuid import uuid4

from apps.api.app.db.session import get_db
from apps.api.app.db.models.video import Video
from apps.api.app.db.models.download_job import DownloadJob
from apps.api.app.workers.queue import queue
from apps.api.app.workers.tasks import download_task
from rq.job import Job
from rq.exceptions import NoSuchJobError
router = APIRouter()


class CreateDownloadReq(BaseModel):
    video_id: str


@router.post("")
def create_download(payload: CreateDownloadReq, db: Session = Depends(get_db)):
    video_id = payload.video_id.strip()
    if not video_id:
        raise HTTPException(400, "video_id is required")

    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "video not found")

    # ✅ 去重策略：
    # 1) 若已有 running/queued job → 直接回傳同一個 job
    stmt = (
        select(DownloadJob)
        .where(DownloadJob.video_id == video_id)
        .where(DownloadJob.status.in_(["queued", "running"]))
        .order_by(DownloadJob.created_at.desc())
    )
    existing = db.execute(stmt).scalars().first()
    if existing:
        # ✅ 若 DB 有 queued/running 但 Redis 沒有這個 RQ job → 視為孤兒 job，補 enqueue
        try:
            Job.fetch(existing.job_id, connection=queue.connection)
        except Exception:
            existing.status = "queued"
            existing.progress = 0
            existing.updated_at = datetime.utcnow()
            db.commit()
            queue.enqueue(download_task, existing.job_id, video_id, job_id=existing.job_id)

        return {"job_id": existing.job_id, "status": existing.status}

    # 2) 若已有 success 且檔案存在 → 直接回傳（不再 enqueue）
    stmt = (
        select(DownloadJob)
        .where(DownloadJob.video_id == video_id)
        .where(DownloadJob.status == "success")
        .order_by(DownloadJob.created_at.desc())
    )
    done = db.execute(stmt).scalars().first()
    if done and done.output_path and os.path.exists(done.output_path):
        return {"job_id": done.job_id, "status": done.status, "output_path": done.output_path}

    # 否則：建立新 job
    job_id = str(uuid4())
    job = DownloadJob(
        job_id=job_id,
        video_id=video_id,
        status="queued",
        progress=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    queue.enqueue(download_task, job_id, video_id, job_id=job_id)
    return {"job_id": job_id, "status": "queued"}

@router.get("/by_video/{video_id}")
def latest_job_by_video(video_id: str, db: Session = Depends(get_db)):
    stmt = (
        select(DownloadJob)
        .where(DownloadJob.video_id == video_id)
        .order_by(DownloadJob.created_at.desc())
        .limit(1)
    )
    job = db.execute(stmt).scalars().first()
    if not job:
        raise HTTPException(404, "job not found")
    return {
        "job_id": job.job_id,
        "video_id": job.video_id,
        "status": job.status,
        "progress": job.progress,
        "output_path": job.output_path,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("/{job_id}")
def get_download(job_id: str, db: Session = Depends(get_db)):
    job = db.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return {
        "job_id": job.job_id,
        "video_id": job.video_id,
        "status": job.status,
        "progress": job.progress,
        "output_path": job.output_path,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
from sqlalchemy import select


# (3) 下載檔案 endpoint
@router.get("/{job_id}/file")
def download_file(job_id: str, db: Session = Depends(get_db)):
    job = db.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status != "success" or not job.output_path:
        raise HTTPException(409, "file is not ready")
    if not os.path.exists(job.output_path):
        raise HTTPException(410, "file missing on disk")

    filename = os.path.basename(job.output_path)
    return FileResponse(path=job.output_path, filename=filename, media_type="video/mp4")




from pydantic import BaseModel
from sqlalchemy import select

class ByVideosReq(BaseModel):
    video_ids: list[str]

@router.post("/by_videos")
def latest_jobs_by_videos(payload: ByVideosReq, db: Session = Depends(get_db)):
    ids = [x.strip() for x in payload.video_ids if x and x.strip()]
    if not ids:
        return []

    # 取每個 video_id 最新的一筆 job（用 created_at 排序後在 python 去重）
    stmt = (
        select(DownloadJob)
        .where(DownloadJob.video_id.in_(ids))
        .order_by(DownloadJob.video_id.asc(), DownloadJob.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()

    latest: dict[str, DownloadJob] = {}
    for j in rows:
        if j.video_id not in latest:
            latest[j.video_id] = j

    return [
        {
            "job_id": j.job_id,
            "video_id": j.video_id,
            "status": j.status,
            "progress": j.progress,
            "output_path": j.output_path,
            "error_message": j.error_message,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
            "created_at": j.created_at,
            "updated_at": j.updated_at,
        }
        for j in latest.values()
    ]