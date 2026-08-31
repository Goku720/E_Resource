import os
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

def make_celery():
    celery = Celery(
        "books_tasks",
        broker=REDIS_URL,
        backend=REDIS_URL
    )

    celery.conf.update(
        task_track_started=True,
        result_expires=3600,
        broker_connection_retry_on_start = True
    )

    return celery

celery = make_celery()