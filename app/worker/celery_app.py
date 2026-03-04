from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "learningpanda",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    # Don't fetch the next task until the current long one finishes
    worker_prefetch_multiplier=1,
    # Acknowledge only after completion so crashed workers requeue the task
    task_acks_late=True,
    # Expose the STARTED state so /status can show "processing"
    task_track_started=True,
    # Keep task results in Redis for 24 hours
    result_expires=86400,
    # Use JSON for cross-language compatibility
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
