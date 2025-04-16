from StudyFlow.backend.celery_worker import celery_app
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
import sqlite3
import os

DB_PATH = "/mnt/data/questions_answers.db"

@celery_app.task(name="StudyFlow.backend.tasks.process_question_async")
def process_question_async(ocr_json):
    try:
        # Validate input: get question text and ensure it's not empty.
        question_text = ocr_json.get("question", "").strip()
        if not question_text:
            raise ValueError("Missing or empty question text in OCR JSON.")
        
        # Get result from AI function
        result = triple_call_ai_api_json_final(ocr_json)
        if result is None:
            raise ValueError("AI function returned None.")
        
        # Convert the result to a string index to lookup answers.
        answers = {str(k): v for k, v in ocr_json.get("answers", {}).items()}
        chosen_index = str(result)
        chosen_answer = answers.get(chosen_index, {}).get("text", "").strip()
        if not chosen_answer:
            raise ValueError(f"Chosen answer text is empty for index {chosen_index}.")


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
        conn.close()
        return result

    except Exception as e:
        # Re-raise exception with a more detailed message for debugging.
        raise Exception(f"Error processing question: {e}")
