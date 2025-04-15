from StudyFlow.backend.celery_worker import celery_app
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
import sqlite3
import os

DB_PATH = "/mnt/data/questions_answers.db"

@celery_app.task(name="StudyFlow.backend.tasks.process_question_async")
def process_question_async(ocr_json):
    question_text = ocr_json.get("question", "").strip()
    result = triple_call_ai_api_json_final(ocr_json)
    chosen_index = str(result)
    answers = ocr_json.get("answers", {})
    chosen_answer = answers.get(chosen_index, {}).get("text", "").strip()

    if question_text and chosen_answer:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO qa_pairs (question, answer, count) VALUES (?, ?, 1)", (question_text, chosen_answer))
        conn.commit()
        conn.close()
    return result
