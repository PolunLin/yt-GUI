from rq import Worker
from apps.api.app.workers.queue import redis_conn

if __name__ == "__main__":
    w = Worker(["downloads"], connection=redis_conn)
    w.work()
