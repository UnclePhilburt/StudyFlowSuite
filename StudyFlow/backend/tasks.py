from StudyFlow.backend.ai_voter import triple_call_ai_api_json_final
from StudyFlow.backend.db_utils import get_db_connection
from celery import Celery
import os

celery_app = Celery("tasks", broker=os.getenv("CELERY_BROKER_URL"))

@celery_app.task()
def process_question_async(ocr_json):
    try:
        print("📥 Received OCR JSON for processing.")

        result = triple_call_ai_api_json_final(ocr_json)

        if not result:
            print("⚠️ No result returned from AI voter.")
            return None

        question_text = result.get("question")
        chosen_answer = result.get("final_answer")

        print(f"🤖 Chosen answer: {chosen_answer}")
        print(f"📖 Question: {question_text}")

        if question_text and chosen_answer:
            conn = get_db_connection()
            cur = conn.cursor()

            # Check if question already exists
            cur.execute("SELECT count FROM qa_pairs WHERE question = ?", (question_text,))
            row = cur.fetchone()

            if row:
                new_count = row["count"] + 1
                cur.execute(
                    "UPDATE qa_pairs SET count = ?, answer = ? WHERE question = ?",
                    (new_count, chosen_answer, question_text)
                )
                print(f"🔁 Updated existing question (new count: {new_count})")
            else:
                cur.execute(
                    "INSERT INTO qa_pairs (question, answer, count) VALUES (?, ?, ?)",
                    (question_text, chosen_answer, 1)
                )
                print("🆕 Inserted new question into database")

            conn.commit()
            conn.close()
        else:
            print("❌ Missing question or answer in result, skipping DB save.")

        return result

    except Exception as e:
        print(f"💥 Error in process_question_async: {e}")
        return None
