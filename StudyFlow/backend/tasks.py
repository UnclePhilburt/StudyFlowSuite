import os
import sqlite3
from celery import Celery
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final

celery_app = Celery("tasks", broker=os.environ.get("CELERY_BROKER_URL"))

DB_PATH = "/mnt/data/questions_answers.db"

def ensure_db_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS qa_pairs (
            question TEXT PRIMARY KEY,
            answer TEXT,
            count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def save_question_to_db(question: str, answer: str):
    if not question or not answer:
        return
    ensure_db_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT count FROM qa_pairs WHERE question = ?", (question,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE qa_pairs SET count = count + 1 WHERE question = ?", (question,))
    else:
        c.execute("INSERT INTO qa_pairs (question, answer, count) VALUES (?, ?, 1)", (question, answer))
    conn.commit()
    conn.close()

@celery_app.task
def process_question_async(ocr_json):
    try:
        result = triple_call_ai_api_json_final(ocr_json)
        if result and "question" in ocr_json and result.get("answer"):
            question = ocr_json["question"]
            answer = result["answer"]
            save_question_to_db(question, answer)
        return result
    except Exception as e:
        return {"error": str(e)}
