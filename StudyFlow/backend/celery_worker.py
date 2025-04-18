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
}
celery_app.conf.task_default_queue = "celery"

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
