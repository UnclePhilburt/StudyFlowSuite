from StudyFlow.backend.celery_worker import celery_app
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
from StudyFlow.backend.supabase_client import create_note_chunk, mark_note_as_processed, make_note_public, get_user_profile
from StudyFlow.backend.text_chunking import chunk_text_smart
from StudyFlow.backend.embedding_client import generate_embeddings_batch
import psycopg2
import os
import json
import google.generativeai as genai

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


@celery_app.task(name="StudyFlow.backend.tasks.process_note_async")
def process_note_async(note_id, user_id, full_text, course_metadata):
    """
    Background task to process uploaded note:
    1. Chunk the text (500 words with 50-word overlap)
    2. Generate embeddings for each chunk
    3. Anonymize chunks for Collective Brain (if user opted in)
    4. Store chunks in Supabase
    """
    try:
        print(f"📝 Processing note {note_id} for user {user_id}")

        # Get user profile to check if they opted into Collective Brain
        user_profile = get_user_profile(user_id)
        if not user_profile:
            raise ValueError(f"User profile not found for {user_id}")

        is_public = user_profile.get("collective_brain_opt_in", False)
        print(f"🌐 Collective Brain opt-in: {is_public}")

        # Step 1: Chunk the text
        chunks = chunk_text_smart(full_text, chunk_size=500, overlap=50)
        print(f"✂️ Created {len(chunks)} chunks")

        if not chunks:
            print("⚠️ No chunks created, marking as processed")
            mark_note_as_processed(note_id)
            return

        # Step 2: Generate embeddings for all chunks
        chunk_texts = [chunk['text'] for chunk in chunks]
        embeddings = generate_embeddings_batch(chunk_texts)

        if len(embeddings) != len(chunks):
            raise ValueError(f"Embedding count mismatch: {len(embeddings)} vs {len(chunks)} chunks")

        print(f"🔢 Generated {len(embeddings)} embeddings")

        # Step 3: Anonymize chunks if user opted into Collective Brain
        anonymized_summaries = []
        if is_public:
            print("🔒 Anonymizing chunks for Collective Brain...")
            anonymized_summaries = anonymize_chunks_batch(chunk_texts)
        else:
            anonymized_summaries = [None] * len(chunks)

        # Step 4: Store chunks in Supabase
        for i, (chunk, embedding, summary) in enumerate(zip(chunks, embeddings, anonymized_summaries)):
            chunk_data = create_note_chunk(
                note_id=note_id,
                user_id=user_id,
                chunk_text=chunk['text'],
                chunk_index=i,
                embedding=embedding,
                course_metadata=course_metadata,
                is_public=is_public
            )

            # Update with anonymized summary if we have one
            if summary and is_public:
                from StudyFlow.backend.supabase_client import supabase
                supabase.table("note_chunks").update({
                    "content_summary": summary,
                    "anonymized_at": "NOW()"
                }).eq("id", chunk_data['id']).execute()

            print(f"💾 Stored chunk {i+1}/{len(chunks)}")

        # Step 5: Mark note as processed
        mark_note_as_processed(note_id)

        # Step 6: Make note public if user opted in
        if is_public:
            make_note_public(note_id, user_id)
            print(f"🌐 Made note public for Collective Brain")

        print(f"✅ Finished processing note {note_id}")

    except Exception as e:
        print(f"❌ Error processing note {note_id}: {e}")
        import traceback
        print(traceback.format_exc())


def anonymize_chunks_batch(chunk_texts):
    """
    Use Gemini to anonymize chunks for Collective Brain.
    Removes personal info, rewrites in generic terms.
    """
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-2.0-flash-exp')

        anonymized = []

        # Process in batches of 5 to avoid overwhelming the API
        batch_size = 5
        for i in range(0, len(chunk_texts), batch_size):
            batch = chunk_texts[i:i + batch_size]

            # Create prompt for batch anonymization
            prompt = f"""You are anonymizing student notes for a shared knowledge base.

Your task: Rewrite these note excerpts to remove ALL personal information while preserving the educational content.

Rules:
1. Remove: Names, dates, personal experiences, specific professors, specific universities
2. Keep: Facts, concepts, definitions, formulas, key ideas
3. Rewrite in neutral, educational tone
4. Keep it concise (similar length to original)

Input chunks (separated by ---):
"""
            for j, chunk in enumerate(batch):
                prompt += f"\n--- Chunk {j+1} ---\n{chunk}\n"

            prompt += """
Return ONLY a JSON array of anonymized chunks in the same order:
["anonymized chunk 1", "anonymized chunk 2", ...]
"""

            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Parse JSON
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]

            batch_anonymized = json.loads(response_text.strip())
            anonymized.extend(batch_anonymized)

            print(f"🔒 Anonymized batch {i//batch_size + 1}")

        return anonymized

    except Exception as e:
        print(f"❌ Error anonymizing chunks: {e}")
        # Return None for all chunks if anonymization fails
        return [None] * len(chunk_texts)
