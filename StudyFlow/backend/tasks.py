import os
import sqlite3
from celery import Celery
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final

celery_app = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND")
)

DB_PATH = "/mnt/data/questions_answers.db"

def init_db():
    """Create the database and table if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qa_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answers TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            count INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_question ON qa_pairs(question)
    ''')
    conn.commit()
    conn.close()

init_db()

def save_to_db(question, answers, correct_answer):
    """Save a question and its answer to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, count FROM qa_pairs WHERE question = ?", (question,))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE qa_pairs SET count = count + 1 WHERE id = ?", (row[0],))
    else:
        cursor.execute(
            "INSERT INTO qa_pairs (question, answers, correct_answer) VALUES (?, ?, ?)",
            (question, str(answers), correct_answer)
        )
    conn.commit()
    conn.close()

@celery_app.task(name="process_question_async")
def process_question_async(ocr_json):
    question = ocr_json["question"]
    answers = ocr_json["answers"]

    result = triple_call_ai_api_json_final(ocr_json)
    chosen_answer = result.get("chosen_answer")

    if question and answers and chosen_answer:
        save_to_db(question, answers, chosen_answer)

    return result
