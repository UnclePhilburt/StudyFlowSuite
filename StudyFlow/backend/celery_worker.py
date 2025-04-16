from celery import Celery
import os

# Set up Celery app
celery_app = Celery(
    "studyflow_tasks",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

# Ensure task routes match the queue your worker listens to
celery_app.conf.task_routes = {
    "StudyFlow.backend.tasks.process_question_async": {"queue": "celery"},
}

# Optional but safe: name your default queue
celery_app.conf.task_default_queue = "celery"
