from StudyFlow.backend.celery_worker import celery_app
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
import sqlite3
import os
import json

DB_PATH = "/mnt/data/questions_answers.db"

@celery_app.task(name="StudyFlow.backend.tasks.process_question_async")
def process_question_async(ocr_json):
    try:
        print("🚀 Task started.")
        print("📥 Received OCR JSON:\n", json.dumps(ocr_json, indent=2))

        question_text = ocr_json.get("question", "").strip()
        if not question_text:
            raise ValueError("Missing or empty question text in OCR JSON.")

        result = triple_call_ai_api_json_final(ocr_json)
        print("🤖 AI voted result:", result)

        if result is None:
            raise ValueError("AI function returned None.")

        answers = {str(k): v for k, v in ocr_json.get("answers", {}).items()}
        chosen_index = str(result)
        chosen_answer = answers.get(chosen_index, {}).get("text", "").strip()

        print(f"🎯 Looking for answer index: {chosen_index}")
        print(f"📝 Chosen answer: {chosen_answer}")

        if not chosen_answer:
            raise ValueError(f"Chosen answer text is empty for index {chosen_index}. Answers dict: {json.dumps(answers, indent=2)}")


        # Insert or update the question-answer pair in the database.
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO qa_pairs (question, answer, count) VALUES (?, ?, 1)",
                (question_text, chosen_answer)
            )
        except sqlite3.IntegrityError:
            # If the question already exists, update its count.
            c.execute(
                "UPDATE qa_pairs SET count = count + 1 WHERE question = ?",
                (question_text,)
            )
        conn.commit()
        print("✅ Wrote to DB:", question_text[:50], "→", chosen_answer[:50])
        conn.close()
        return result

    except Exception as e:
        # Re-raise exception with a more detailed message for debugging.
        raise Exception(f"Error processing question: {e}")
