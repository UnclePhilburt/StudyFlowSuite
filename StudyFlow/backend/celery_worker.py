from celery import Celery
import os

# Configure the Celery app
celery_app = Celery(
    "studyflow_tasks",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

celery_app.conf.task_routes = {
    "StudyFlow.backend.tasks.process_question_async": {"queue": "default"},
}
