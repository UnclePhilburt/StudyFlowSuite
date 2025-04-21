from StudyFlow.backend.celery_worker import celery_app
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
import psycopg2
import os
import json

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

        # Insert or update into Postgres
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO qa_pairs (question, answer, count)
                VALUES (%s, %s, 1)
                ON CONFLICT (question)
                DO UPDATE SET count = qa_pairs.count + 1
            """, (question_text, chosen_answer))
            conn.commit()
            print("💾 Stored question and answer in Postgres.")
        finally:
            conn.close()

        # ✅ Return chosen index so the frontend gets it
        return int(chosen_index)

    except Exception as e:
        print("❌ Error in task:", str(e))
