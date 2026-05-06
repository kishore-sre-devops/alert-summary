
import os
from celery import Celery

# Using environment variables for configuration is a good practice.
# This allows for flexibility in different environments (development, production).
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "smclama_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.workers.metric_worker",
        "app.workers.notification_worker"
    ],
)

celery_app.conf.update(
    task_track_started=True,
    # This ensures that if the worker starts before the broker (Redis),
    # it will keep retrying to connect instead of crashing.
    broker_connection_retry_on_startup=True,
)

if __name__ == "__main__":
    celery_app.start()
