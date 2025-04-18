from celery import Celery
import os
import sqlite3

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

# ✅ Ensure DB and count column are present
def ensure_db_ready():
    os.makedirs("/mnt/data", exist_ok=True)
    conn = sqlite3.connect("/mnt/data/questions_answers.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS qa_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT UNIQUE,
            answer TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        c.execute("ALTER TABLE qa_pairs ADD COLUMN count INTEGER DEFAULT 1")
        print("✅ 'count' column added to qa_pairs")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ 'count' column already exists.")
        else:
            print(f"❌ Error adding count column: {e}")
    conn.commit()
    conn.close()

ensure_db_ready()
