from celery import Celery
import os

print("🔍 WEB sees CELERY_BROKER_URL =", os.getenv("CELERY_BROKER_URL"))

# Get Redis URL from environment variable
redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
print(f"🔌 Connecting to Redis at: {redis_url}")  # Optional debug log

# Set up Celery app
celery_app = Celery(
    "studyflow_tasks",
    broker=redis_url,
    backend=redis_url
)

# Ensure task routes match the queue your worker listens to
celery_app.conf.task_routes = {
    "StudyFlow.backend.tasks.process_question_async": {"queue": "celery"},
}

# Optional but safe: name your default queue
celery_app.conf.task_default_queue = "celery"
