from celery import Celery
def make_celery():
    celery = Celery(
        "books_tasks",
        broker="redis://localhost:6379/0",
        backend="redis://localhost:6379/0"
    )

    celery.conf.update(
        task_track_started=True,
        result_expires=3600,
        broker_connection_retry_on_start = True
    )

    return celery

celery = make_celery()