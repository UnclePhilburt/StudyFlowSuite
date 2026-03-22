"""
Conversational NoteFlow - AI Chat with Memory (Database-backed)
Allows students to have back-and-forth conversations about their notes with persistent history
"""
import os
import uuid
from typing import Dict, List, Optional
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.supabase_client import supabase


def create_conversation(user_id: str) -> str:
    """Create a new conversation in the database and return its ID"""
    try:
        conv_id = str(uuid.uuid4())

        response = supabase.table("conversations").insert({
            "id": conv_id,
            "user_id": user_id,
            "title": None  # Will be auto-generated from first message
        }).execute()

        debug_log(f"💬 Created conversation {conv_id} for user {user_id}")
        return conv_id

    except Exception as e:
        debug_log(f"❌ Error creating conversation: {e}")
        return None


def get_conversation(conv_id: str, user_id: str) -> Optional[Dict]:
    """Get a conversation by ID (verifies ownership)"""
    try:
        response = supabase.table("conversations").select("*").eq("id", conv_id).eq("user_id", user_id).single().execute()
        return response.data if response.data else None

    except Exception as e:
        debug_log(f"❌ Error getting conversation: {e}")
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
    """List all conversations for a user, ordered by most recent"""
    try:
        response = supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(limit).execute()

        return response.data if response.data else []

    except Exception as e:
        debug_log(f"❌ Error listing conversations: {e}")
        return []


def delete_conversation(conv_id: str, user_id: str) -> bool:
    """Delete a conversation and all its messages"""
    try:
        # Verify ownership
        conv = get_conversation(conv_id, user_id)
        if not conv:
            return False

        # Delete conversation (CASCADE will delete messages)
        supabase.table("conversations").delete().eq("id", conv_id).eq("user_id", user_id).execute()

        debug_log(f"🗑️ Deleted conversation {conv_id}")
        return True

    except Exception as e:
        debug_log(f"❌ Error deleting conversation: {e}")
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
        debug_log(f"✅ Generated conversation title: {title}")
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
) -> str:
    """
    Generate a conversational AI response using retrieved context

    Args:
        question: Student's question
        search_results: Relevant chunks from database
        conversation_history: Previous messages in conversation

    Returns:
        AI-generated conversational response
    """
    try:
        import google.generativeai as genai
        import os

        # Configure Gemini
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            debug_log("❌ GEMINI_API_KEY not found in environment!")
            raise ValueError("GEMINI_API_KEY not configured")

        genai.configure(api_key=gemini_api_key)

        # Build context from search results and collect contributor usernames
        context_chunks = []
        contributors = set()  # Use set to avoid duplicates
        for result in search_results[:3]:  # Use top 3 results
            text = result.get('content_summary') or result.get('chunk_text', '')
            context_chunks.append(text)

            # Collect username if available
            if result.get('username'):
                contributors.add(result.get('username'))

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
7. If you don't have information to answer, say you don't have enough context and suggest they ask a more specific question

Be thorough and educational - give students the full picture with 3-5 paragraphs of detailed explanation. Don't hold back information."""

        if context:
            prompt = f"""{system_instruction}

Previous conversation:
{conversation_context}

Student Question: {question}

Context to answer from:
{context}

Answer the question naturally, as if you're a tutor who knows this information."""
        else:
            prompt = f"""{system_instruction}

Previous conversation:
{conversation_context}

Student Question: {question}

No relevant context found. Politely let them know you don't have information about this topic."""

        debug_log(f"🤖 Generating conversational response with Gemini 3.1 Flash-Lite ({len(search_results)} context chunks)")

        # Call Gemini 3.1 Flash-Lite (cheapest + fastest)
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=1500  # Increased for detailed responses
            )
        )

        answer = response.text

        # Add contributor attribution if we have contributors
        if contributors:
            contributor_list = ", ".join([f"@{username}" for username in sorted(contributors)])
            answer += f"\n\n---\n*This summary was synthesized from the Nexus, featuring insights from {contributor_list}.*"

        debug_log(f"✅ Generated {len(answer)} character response with Gemini")

        return answer

    except Exception as e:
        debug_log(f"❌ Error generating conversational response: {e}")
        import traceback
        debug_log(traceback.format_exc())

        # Fallback to simple response
        if search_results:
            return f"I found some information about that. {search_results[0].get('content_summary', 'Check your notes for more details.')}"
        else:
            return "I couldn't find anything about that in your notes. Try rephrasing your question or upload more notes!"
