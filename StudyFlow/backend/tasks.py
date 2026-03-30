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
def process_note_async(note_id, user_id, full_text, course_metadata, file_hash=None, username=None):
    """
    Background task to process uploaded note:
    1. Chunk the text (500 words with 50-word overlap)
    2. Generate embeddings for each chunk
    3. Anonymize chunks for Nexus (if user opted in)
    4. Store chunks in Supabase
    """
    try:
        print(f"Processing note {note_id} for user {user_id}")

        # Get user profile to check if they opted into Nexus
        user_profile = get_user_profile(user_id)
        if not user_profile:
            raise ValueError(f"User profile not found for {user_id}")

        is_public = user_profile.get("collective_brain_opt_in", False)

        # Get username from profile if not provided
        if not username:
            username = user_profile.get("username")

        print(f"Nexus opt-in: {is_public} (@{username})")

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

        # Step 3: Anonymize chunks if user opted into Nexus
        anonymized_summaries = []
        if is_public:
            print("🔒 Anonymizing chunks for Nexus...")
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
                is_public=is_public,
                username=username
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
            print(f"Made note public for Nexus")

        # Step 7: Mark upload log as AI-processed (Missouri SB 1324 compliance)
        if file_hash:
            from StudyFlow.backend.supabase_client import mark_upload_as_processed
            mark_upload_as_processed(file_hash)

        print(f"Finished processing note {note_id}")

    except Exception as e:
        print(f"Error processing note {note_id}: {e}")
        import traceback
        print(traceback.format_exc())


@celery_app.task(name="StudyFlow.backend.tasks.update_note_votes")
def update_note_votes(note_ids):
    """
    Recalculate net_votes for specific notes after a vote is cast.
    Called from the rate-response endpoint.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Fetch all ratings that cite any of these notes
        ratings_resp = supabase.table("ai_response_ratings").select("vote, cited_note_ids").execute()
        ratings = ratings_resp.data or []

        # Aggregate votes per note
        vote_map = {}
        for rating in ratings:
            for nid in (rating.get("cited_note_ids") or []):
                if nid in note_ids:
                    if nid not in vote_map:
                        vote_map[nid] = 0
                    vote_map[nid] += rating["vote"]

        # Update each note's net_votes
        for nid in note_ids:
            net = vote_map.get(nid, 0)
            supabase.table("notes").update({"net_votes": net}).eq("id", nid).execute()

        print(f"Updated net_votes for {len(note_ids)} notes")

    except Exception as e:
        print(f"Error updating note votes: {e}")
        import traceback
        print(traceback.format_exc())


@celery_app.task(name="StudyFlow.backend.tasks.backfill_all_vote_counts")
def backfill_all_vote_counts():
    """
    Periodic task: recalculate net_votes for ALL notes.
    Runs hourly to keep counts accurate.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Fetch all ratings
        ratings_resp = supabase.table("ai_response_ratings").select("vote, cited_note_ids").execute()
        ratings = ratings_resp.data or []

        # Aggregate all votes
        vote_map = {}
        for rating in ratings:
            for nid in (rating.get("cited_note_ids") or []):
                if nid not in vote_map:
                    vote_map[nid] = 0
                vote_map[nid] += rating["vote"]

        # Update notes that have votes
        updated = 0
        for nid, net in vote_map.items():
            try:
                supabase.table("notes").update({"net_votes": net}).eq("id", nid).execute()
                updated += 1
            except:
                pass

        # Reset notes that no longer have votes
        if vote_map:
            # Get all notes with non-zero net_votes that aren't in vote_map
            noted_resp = supabase.table("notes").select("id").neq("net_votes", 0).execute()
            for n in (noted_resp.data or []):
                if n["id"] not in vote_map:
                    try:
                        supabase.table("notes").update({"net_votes": 0}).eq("id", n["id"]).execute()
                    except:
                        pass

        print(f"Backfill complete: updated {updated} notes with vote counts")

    except Exception as e:
        print(f"Error backfilling votes: {e}")
        import traceback
        print(traceback.format_exc())


@celery_app.task(name="StudyFlow.backend.tasks.send_citation_notifications")
def send_citation_notifications(sources, requesting_user_id):
    """
    Background task: notify note owners when their notes are cited in chat.
    Moved out of the request cycle to speed up chat responses.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from datetime import datetime, timedelta

        for src in (sources or []):
            src_note_id = src.get("note_id")
            if not src_note_id:
                continue

            try:
                note_row = supabase.table("notes").select("user_id, original_filename").eq("id", src_note_id).execute()
                if not note_row.data:
                    continue

                owner_id = note_row.data[0].get("user_id")
                if not owner_id or owner_id == requesting_user_id:
                    continue

                # Skip duplicate citation notifications within 24 hours
                cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
                existing = supabase.table("notifications") \
                    .select("id") \
                    .eq("user_id", owner_id) \
                    .eq("type", "note_cited") \
                    .eq("note_id", src_note_id) \
                    .gte("created_at", cutoff) \
                    .limit(1) \
                    .execute()

                if existing.data:
                    continue

                fname = note_row.data[0].get("original_filename", "your note")
                supabase.table("notifications").insert({
                    "user_id": owner_id,
                    "type": "note_cited",
                    "title": "Note Cited",
                    "message": f"Your note {fname} was cited in a chat",
                    "note_id": src_note_id,
                    "is_read": False
                }).execute()

                print(f"Sent citation notification to {owner_id} for note {src_note_id}")
            except Exception as e:
                print(f"Citation notification error for {src_note_id}: {e}")
                continue

    except Exception as e:
        print(f"Citation notifications task error: {e}")


@celery_app.task(name="StudyFlow.backend.tasks.update_view_download_counts")
def update_view_download_counts():
    """
    Periodic task: recalculate view_count and download_count for all notes.
    Runs every 30 minutes so browse endpoint reads columns instead of counting.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Get all view counts
        views_resp = supabase.table("note_views").select("note_id").execute()
        view_counts = {}
        for v in (views_resp.data or []):
            nid = v['note_id']
            view_counts[nid] = view_counts.get(nid, 0) + 1

        # Get all download counts
        dl_resp = supabase.table("download_transactions").select("note_id").execute()
        dl_counts = {}
        for d in (dl_resp.data or []):
            nid = d['note_id']
            dl_counts[nid] = dl_counts.get(nid, 0) + 1

        # Get all note IDs that have counts
        all_ids = set(list(view_counts.keys()) + list(dl_counts.keys()))

        updated = 0
        for nid in all_ids:
            try:
                update = {}
                if nid in view_counts:
                    update["view_count"] = view_counts[nid]
                if nid in dl_counts:
                    update["download_count"] = dl_counts[nid]
                if update:
                    supabase.table("notes").update(update).eq("id", nid).execute()
                    updated += 1
            except:
                pass

        # Reset counts for notes that no longer have views/downloads
        try:
            noted_resp = supabase.table("notes").select("id, view_count, download_count").execute()
            for n in (noted_resp.data or []):
                reset = {}
                if n.get('view_count', 0) > 0 and n['id'] not in view_counts:
                    reset['view_count'] = 0
                if n.get('download_count', 0) > 0 and n['id'] not in dl_counts:
                    reset['download_count'] = 0
                if reset:
                    supabase.table("notes").update(reset).eq("id", n['id']).execute()
        except:
            pass

        print(f"Updated view/download counts for {updated} notes")

    except Exception as e:
        print(f"View/download count update error: {e}")
        import traceback
        print(traceback.format_exc())


@celery_app.task(name="StudyFlow.backend.tasks.keep_warm")
def keep_warm():
    """Periodic ping to prevent Render cold starts."""
    try:
        import urllib.request
        backend_url = os.getenv("RENDER_EXTERNAL_URL", "https://studyflowsuite.onrender.com")
        urllib.request.urlopen(backend_url + "/health", timeout=10)
        print("Server warm ping OK")
    except Exception as e:
        print(f"Warm ping failed: {e}")


@celery_app.task(name="StudyFlow.backend.tasks.prewarm_cache")
def prewarm_cache():
    """Pre-load frequently accessed data into Redis on startup/periodically."""
    try:
        import redis
        from StudyFlow.backend.supabase_client import supabase

        url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r = redis.from_url(url, decode_responses=True)

        # 1. Pre-cache the most active user profiles
        try:
            # Get users who have public notes (most likely to appear in search results)
            notes_resp = supabase.table("notes").select("user_id").eq("is_public", True).limit(200).execute()
            user_ids = list(set(n['user_id'] for n in (notes_resp.data or []) if n.get('user_id')))

            if user_ids:
                profiles_resp = supabase.table("user_profiles").select("id, username, is_public").in_("id", user_ids).execute()
                cached = 0
                for p in (profiles_resp.data or []):
                    profile_data = json.dumps({
                        "username": p.get("username") or "Anonymous",
                        "is_public": p.get("is_public", True)
                    })
                    r.setex(f"profile:{p['id']}", 600, profile_data)
                    cached += 1
                print(f"Pre-warmed {cached} user profiles")
        except Exception as e:
            print(f"Profile pre-warm error: {e}")

        # 2. Pre-cache popular browse results (recent notes, no filter)
        try:
            import urllib.request
            backend_url = os.getenv("RENDER_EXTERNAL_URL", "https://studyflowsuite.onrender.com")
            # Trigger a browse request to populate the cache
            # This will be cached by the browse endpoint's Redis logic
            print("Pre-warm: browse cache will populate on first request")
        except:
            pass

        print("Cache pre-warm complete")

    except Exception as e:
        print(f"Pre-warm error: {e}")
        import traceback
        print(traceback.format_exc())


def anonymize_chunks_batch(chunk_texts):
    """
    Use Gemini to anonymize chunks for Nexus.
    Removes personal info, rewrites in generic terms.
    """
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-3-flash-preview')

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

            try:
                from StudyFlow.backend.cost_tracker import track_ai_call
                track_ai_call("gemini", "flash", "anonymization")
            except:
                pass

            print(f"Anonymized batch {i//batch_size + 1}")

        return anonymized

    except Exception as e:
        print(f"❌ Error anonymizing chunks: {e}")
        # Return None for all chunks if anonymization fails
        return [None] * len(chunk_texts)
