from celery import Celery
import os
import psycopg2

print("🔍 WEB sees CELERY_BROKER_URL =", os.getenv("CELERY_BROKER_URL"))

# Redis for Celery
redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
print(f"🔌 Connecting to Redis at: {redis_url}")

# Celery setup
celery_app = Celery(
    "studyflow_tasks",
    broker=redis_url,
    backend=redis_url
)

celery_app.conf.task_routes = {
    "StudyFlow.backend.tasks.process_question_async": {"queue": "celery"},
    "StudyFlow.backend.tasks.update_note_votes": {"queue": "celery"},
    "StudyFlow.backend.tasks.backfill_all_vote_counts": {"queue": "celery"},
    "StudyFlow.backend.tasks.keep_warm": {"queue": "celery"},
    "StudyFlow.backend.tasks.prewarm_cache": {"queue": "celery"},
    "StudyFlow.backend.tasks.send_citation_notifications": {"queue": "celery"},
    "StudyFlow.backend.tasks.update_view_download_counts": {"queue": "celery"},
}
celery_app.conf.task_default_queue = "celery"

# Periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "keep-render-warm": {
        "task": "StudyFlow.backend.tasks.keep_warm",
        "schedule": 300.0,  # Every 5 minutes
    },
    "backfill-votes-hourly": {
        "task": "StudyFlow.backend.tasks.backfill_all_vote_counts",
        "schedule": 3600.0,  # Every hour
    },
    "prewarm-cache": {
        "task": "StudyFlow.backend.tasks.prewarm_cache",
        "schedule": 900.0,  # Every 15 minutes
    },
    "update-view-download-counts": {
        "task": "StudyFlow.backend.tasks.update_view_download_counts",
        "schedule": 1800.0,  # Every 30 minutes
    },
}
celery_app.conf.timezone = "UTC"

# Postgres DB check (optional)
def ensure_db_ready():
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qa_pairs (
                id SERIAL PRIMARY KEY,
                question TEXT UNIQUE,
                answer TEXT,
                count INTEGER DEFAULT 1,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print("✅ PostgreSQL: qa_pairs table ready.")
    except Exception as e:
        print(f"❌ PostgreSQL setup error: {e}")

ensure_db_ready()
