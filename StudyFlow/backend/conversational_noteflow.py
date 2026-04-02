"""
Conversational NoteFlow - AI Chat with Memory (Database-backed)
Allows students to have back-and-forth conversations about their notes with persistent history
"""
import os
import uuid
from typing import Dict, List, Optional
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.supabase_client import supabase


def create_conversation(user_id: str, source: str = "chat") -> str:
    """Create a new conversation in the database and return its ID.

    Args:
        user_id: The user's ID
        source: Where this conversation originated - 'chat' or 'plugin'
    """
    try:
        conv_id = str(uuid.uuid4())

        response = supabase.table("conversations").insert({
            "id": conv_id,
            "user_id": user_id,
            "title": None,  # Will be auto-generated from first message
            "source": source
        }).execute()

        debug_log(f"💬 Created conversation {conv_id} for user {user_id}")
        return conv_id

    except Exception as e:
        debug_log(f"❌ Error creating conversation: {e}")
        return None


def get_conversation(conv_id: str, user_id: str) -> Optional[Dict]:
    """Get a conversation by ID (verifies ownership, excludes soft-deleted)"""
    try:
        response = supabase.table("conversations").select("*").eq("id", conv_id).eq("user_id", user_id).is_("deleted_at", "null").execute()
        return response.data[0] if response.data else None

    except Exception as e:
        debug_log(f"[-] Error getting conversation: {e}")
        return None


def get_conversation_messages(conv_id: str, user_id: str) -> List[Dict]:
    """Get all messages in a conversation"""
    try:
        # Verify user owns this conversation
        conv = get_conversation(conv_id, user_id)
        if not conv:
            return None  # Return None to indicate conversation not found or access denied

        # Get messages ordered by creation time
        response = supabase.table("conversation_messages").select("*").eq("conversation_id", conv_id).order("created_at").execute()

        return response.data if response.data else []

    except Exception as e:
        debug_log(f"❌ Error getting conversation messages: {e}")
        return None


def add_message(conv_id: str, role: str, content: str, sources: List[Dict] = None):
    """Add a message to conversation history in database"""
    try:
        supabase.table("conversation_messages").insert({
            "conversation_id": conv_id,
            "role": role,
            "content": content,
            "sources": sources or []
        }).execute()

        debug_log(f"💬 Added {role} message to conversation {conv_id}")

    except Exception as e:
        debug_log(f"❌ Error adding message: {e}")


def list_user_conversations(user_id: str, limit: int = 20) -> List[Dict]:
    """List chat conversations for a user, ordered by most recent (excludes soft-deleted and plugin conversations)"""
    try:
        response = supabase.table("conversations").select("*").eq("user_id", user_id).eq("source", "chat").is_("deleted_at", "null").order("updated_at", desc=True).limit(limit).execute()

        return response.data if response.data else []

    except Exception as e:
        debug_log(f"[-] Error listing conversations: {e}")
        return []


def delete_conversation(conv_id: str, user_id: str) -> bool:
    """Soft-delete a conversation (7-year retention for Missouri SB 1324 compliance)"""
    try:
        # Verify ownership
        conv = get_conversation(conv_id, user_id)
        if not conv:
            return False

        # Soft delete -- mark as deleted but keep data for compliance
        from datetime import datetime
        supabase.table("conversations").update({
            "deleted_at": datetime.utcnow().isoformat()
        }).eq("id", conv_id).eq("user_id", user_id).execute()

        debug_log(f"[*] Soft-deleted conversation {conv_id} (retained for compliance)")
        return True

    except Exception as e:
        debug_log(f"[-] Error deleting conversation: {e}")
        return False


def generate_conversation_title(question: str, answer: str) -> str:
    """Generate a short, descriptive title for the conversation using AI"""
    try:
        import google.generativeai as genai

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            debug_log("❌ GEMINI_API_KEY not found, using fallback title")
            return question[:50]

        genai.configure(api_key=gemini_api_key)

        prompt = f"""Generate a very short, descriptive title (3-5 words max) for this conversation.

Question: {question}
Answer: {answer}

Title should be concise and capture the main topic. Do not use quotes. Just return the title text.

Examples:
- "DNA Replication Process"
- "World War I Causes"
- "Photosynthesis Explained"
- "Algebra Equations Help"

Title:"""

        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=20
            )
        )

        title = response.text.strip().strip('"').strip("'")
        debug_log(f"Generated conversation title: {title}")

        try:
            from StudyFlow.backend.cost_tracker import track_ai_call
            track_ai_call("gemini", "flash-lite", "title_gen")
        except:
            pass

        return title

    except Exception as e:
        debug_log(f"❌ Error generating title: {e}")
        # Fallback to first 50 chars of question
        return question[:50]


def update_conversation_title(conv_id: str, title: str):
    """Update the title of a conversation"""
    try:
        supabase.table("conversations").update({
            "title": title
        }).eq("id", conv_id).execute()

        debug_log(f"📝 Updated conversation {conv_id} title to: {title}")

    except Exception as e:
        debug_log(f"❌ Error updating conversation title: {e}")


def generate_conversational_response(
    question: str,
    search_results: List[Dict],
    conversation_history: List[Dict]
) -> Dict:
    """
    Generate a conversational AI response using retrieved context

    Args:
        question: Student's question
        search_results: Relevant chunks from database
        conversation_history: Previous messages in conversation

    Returns:
        Dict with keys: response (str), model_used (str), response_time_ms (int)
    """
    try:
        import google.generativeai as genai
        import os
        import time

        # Configure Gemini
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            debug_log("❌ GEMINI_API_KEY not found in environment!")
            raise ValueError("GEMINI_API_KEY not configured")

        genai.configure(api_key=gemini_api_key)

        # Build context from search results and collect contributor usernames + Wikipedia articles
        context_chunks = []
        contributors = set()  # Use set to avoid duplicates
        wikipedia_articles = []  # Track Wikipedia articles for attribution
        student_note_count = 0  # Count student notes without usernames

        # Use top 3 results for context, but collect ALL contributors for consensus citation
        for i, result in enumerate(search_results):
            # Only use first 3 for actual context
            if i < 3:
                text = result.get('content_summary') or result.get('chunk_text', '')
                context_chunks.append(text)

            # Collect ALL contributors (not just first 3) for consensus attribution
            # Check if this is a Wikipedia source
            if result.get('university') == 'Wikipedia':
                # Extract article title from original_filename (stored in result during search)
                if result.get('original_filename'):
                    article_title = result['original_filename'].replace('.txt', '')
                    if article_title not in wikipedia_articles:  # Avoid duplicates
                        wikipedia_articles.append(article_title)
            else:
                # Collect username if available (for student notes)
                if result.get('username'):
                    contributors.add(result.get('username'))
                else:
                    # Count anonymous student notes
                    if i < 3:  # Only count anonymous notes in context
                        student_note_count += 1

        context = "\n\n".join(context_chunks)

        # Build conversation history for Gemini
        conversation_context = ""
        for msg in conversation_history[-6:]:  # Last 6 messages
            role = "Student" if msg['role'] == 'user' else "Tutor"
            conversation_context += f"{role}: {msg['content']}\n\n"

        # Build the full prompt for Gemini
        system_instruction = """You are a comprehensive study tutor. Students ask you questions and you provide detailed, thorough explanations like a knowledgeable professor.

Your job:
1. Provide DETAILED, COMPREHENSIVE answers using all the provided context
2. Explain concepts thoroughly with definitions, examples, and context
3. Include all relevant facts, mechanisms, and supporting details
4. Be conversational and friendly, but prioritize completeness over brevity
5. For follow-up questions, expand even further with additional depth
6. Never say "according to your notes" or mention source files - just answer naturally as if you know this information
7. Never apologize for lack of context or ask for more details - just answer based on what you have
8. DO NOT say things like "I don't have your specific course notes" or "I need more context" - be confident and answer directly
9. PRIORITY: Always prioritize information from the student's own uploaded notes and other students' notes over supplemental Wikipedia content. Wikipedia context is provided only as background knowledge when student notes are limited on a topic.

Be thorough and educational - give students the full picture with 3-5 paragraphs of detailed explanation. Don't hold back information."""

        if context:
            prompt = f"""{system_instruction}

Previous conversation:
{conversation_context}

Student Question: {question}

Context from notes:
{context}

Answer the student's question above. Use the relevant parts of the context that directly relate to what they asked. If the context doesn't match their question, acknowledge that and answer what you can."""
        else:
            prompt = f"""{system_instruction}

Previous conversation:
{conversation_context}

Student Question: {question}

No relevant notes found in the database. Briefly let them know you don't have information about this specific topic in their uploaded notes."""

        debug_log(f"[*] Generating conversational response with Gemini 3.1 Flash-Lite ({len(search_results)} context chunks)")

        # Call Gemini 3.1 Flash-Lite (cheapest + fastest)
        model_name = 'gemini-3.1-flash-lite-preview'
        model = genai.GenerativeModel(model_name)

        start_time = time.time()
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=1500  # Increased for detailed responses
            )
        )
        response_time_ms = int((time.time() - start_time) * 1000)

        answer = response.text

        # Track cost
        try:
            from StudyFlow.backend.cost_tracker import track_ai_call
            track_ai_call("gemini", "flash-lite", "chat")
        except:
            pass

        # Build attribution footer with Wikipedia links and student contributors
        from datetime import datetime

        attribution_parts = []

        # Build the main attribution line - ALWAYS show sources
        if wikipedia_articles and contributors:
            # Both Wikipedia and student notes with usernames
            wiki_links = []
            for article in wikipedia_articles[:3]:  # Max 3 Wikipedia articles
                # URL-encode the article title (replace spaces with underscores)
                url_title = article.replace(' ', '_')
                wiki_link = f"[{article}](https://en.wikipedia.org/wiki/{url_title})"
                wiki_links.append(wiki_link)

            wiki_text = ", ".join(wiki_links)
            contributor_list = ", ".join([f"@{username}" for username in sorted(contributors)])

            attribution_parts.append(f"*This summary was synthesized from the Nexus and Wikipedia: {wiki_text}, featuring insights from {contributor_list}.*")

        elif wikipedia_articles and student_note_count > 0:
            # Both Wikipedia and student notes without usernames
            wiki_links = []
            for article in wikipedia_articles[:3]:
                url_title = article.replace(' ', '_')
                wiki_link = f"[{article}](https://en.wikipedia.org/wiki/{url_title})"
                wiki_links.append(wiki_link)

            wiki_text = ", ".join(wiki_links)
            attribution_parts.append(f"*This summary was synthesized from the Nexus and Wikipedia: {wiki_text}.*")

        elif wikipedia_articles:
            # Wikipedia only
            wiki_links = []
            for article in wikipedia_articles[:3]:
                url_title = article.replace(' ', '_')
                wiki_link = f"[{article}](https://en.wikipedia.org/wiki/{url_title})"
                wiki_links.append(wiki_link)

            wiki_text = ", ".join(wiki_links)
            attribution_parts.append(f"*This summary was synthesized from Wikipedia: {wiki_text}.*")

        elif contributors:
            # Student notes with usernames
            contributor_list = ", ".join([f"@{username}" for username in sorted(contributors)])
            attribution_parts.append(f"*This summary was synthesized from the Nexus, featuring insights from {contributor_list}.*")

        elif student_note_count > 0:
            # Student notes without usernames (anonymous contributions)
            attribution_parts.append(f"*This summary was synthesized from {student_note_count} {'note' if student_note_count == 1 else 'notes'} in the Nexus.*")

        elif not search_results or len(search_results) == 0:
            # No sources found - AI generated from general knowledge
            attribution_parts.append(f"*This response was generated using AI. No specific sources were found in the Nexus. Consider uploading relevant notes!*")

        # Add Wikipedia CC BY-SA compliance footer if Wikipedia sources used
        if wikipedia_articles:
            today = datetime.now().strftime("%B %d, %Y")
            attribution_parts.append(f"*Wikipedia content retrieved on {today}. Licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).*")

        # ALWAYS append attribution to answer
        answer += "\n\n---\n" + "\n\n".join(attribution_parts)

        debug_log(f"[+] Generated {len(answer)} character response with Gemini in {response_time_ms}ms")

        # Generate 2 smart follow-up suggestions
        followup_suggestions = []
        try:
            followup_prompt = f"""Based on this Q&A, suggest exactly 2 short follow-up questions the student might ask next. Make them specific to the topic, not generic.

Question: {question}
Answer: {answer[:500]}

Return ONLY a JSON array of 2 strings, nothing else:
["follow-up question 1", "follow-up question 2"]"""

            followup_resp = model.generate_content(
                followup_prompt,
                generation_config=genai.GenerationConfig(temperature=0.8, max_output_tokens=150)
            )
            import json as _json
            ft = followup_resp.text.strip()
            if ft.startswith('```'): ft = ft.split('\n', 1)[1] if '\n' in ft else ft[3:]
            if ft.endswith('```'): ft = ft[:-3]
            followup_suggestions = _json.loads(ft.strip())[:2]

            track_ai_call("gemini", "flash-lite", "followup_gen")
        except:
            followup_suggestions = []

        return {
            "response": answer,
            "model_used": model_name,
            "response_time_ms": response_time_ms,
            "followup_suggestions": followup_suggestions
        }

    except Exception as e:
        debug_log(f"[-] Error generating conversational response: {e}")
        import traceback
        debug_log(traceback.format_exc())

        # Fallback to simple response
        if search_results:
            fallback = f"I found some information about that. {search_results[0].get('content_summary', 'Check your notes for more details.')}"
        else:
            fallback = "I couldn't find anything about that in your notes. Try rephrasing your question or upload more notes!"

        return {
            "response": fallback,
            "model_used": "fallback",
            "response_time_ms": 0
        }
