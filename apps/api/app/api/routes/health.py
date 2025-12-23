from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import redis
import os

from apps.api.app.db.session import get_db

router = APIRouter()

@router.get("")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    r.ping()
    return {"ok": True}