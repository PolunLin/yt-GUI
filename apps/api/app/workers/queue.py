import os
from redis import Redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_conn = Redis.from_url(REDIS_URL)

queue = Queue("downloads", connection=redis_conn, default_timeout=10 * 60)
scan_queue = Queue("scans", connection=redis_conn, default_timeout=10 * 60)  # ✅ 加 timeout