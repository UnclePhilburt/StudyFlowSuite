"""
Conversational NoteFlow - AI Chat with Memory
Allows students to have back-and-forth conversations about their notes
"""
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from StudyFlow.logging_utils import debug_log

# In-memory conversation store (use Redis in production for multi-server)
conversations: Dict[str, Dict] = {}

# Cleanup old conversations (older than 1 hour)
def cleanup_old_conversations():
    """Remove conversations older than 1 hour"""
    cutoff = datetime.now() - timedelta(hours=1)
    to_delete = [
        conv_id for conv_id, conv in conversations.items()
        if conv.get('last_updated', datetime.now()) < cutoff
    ]
    for conv_id in to_delete:
        del conversations[conv_id]
    if to_delete:
        debug_log(f"🧹 Cleaned up {len(to_delete)} old conversations")


def create_conversation(user_id: str) -> str:
    """Create a new conversation and return its ID"""
    cleanup_old_conversations()

    conv_id = str(uuid.uuid4())
    conversations[conv_id] = {
        'user_id': user_id,
        'messages': [],
        'created_at': datetime.now(),
        'last_updated': datetime.now()
    }
    debug_log(f"💬 Created conversation {conv_id} for user {user_id}")
    return conv_id


def get_conversation(conv_id: str, user_id: str) -> Optional[Dict]:
    """Get a conversation by ID (verifies ownership)"""
    conv = conversations.get(conv_id)
    if conv and conv['user_id'] == user_id:
        return conv
    return None


def add_message(conv_id: str, role: str, content: str, sources: List[Dict] = None):
    """Add a message to conversation history"""
    if conv_id in conversations:
        conversations[conv_id]['messages'].append({
            'role': role,
            'content': content,
            'sources': sources or [],
            'timestamp': datetime.now()
        })
        conversations[conv_id]['last_updated'] = datetime.now()


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

        # Build context from search results
        context_chunks = []
        for result in search_results[:3]:  # Use top 3 results
            text = result.get('content_summary') or result.get('chunk_text', '')
            context_chunks.append(text)

        context = "\n\n".join(context_chunks)

        # Build conversation history for Gemini
        conversation_context = ""
        for msg in conversation_history[-6:]:  # Last 6 messages
            role = "Student" if msg['role'] == 'user' else "Tutor"
            conversation_context += f"{role}: {msg['content']}\n\n"

        # Build the full prompt for Gemini
        system_instruction = """You are a helpful study tutor. Students ask you questions and you answer naturally, like a knowledgeable teacher.

Your job:
1. Answer questions directly using the provided context - speak as if you just know the information
2. Be conversational and friendly, like a real tutor
3. Explain concepts clearly with examples when helpful
4. For follow-up questions like "can you explain more" or "be more specific", expand on the previous topic with more detail
5. Never say "according to your notes" or mention source files - just answer naturally
6. If you don't have information to answer, say you don't have enough context and suggest they ask a more specific question

Keep responses concise (2-3 paragraphs max) unless they explicitly ask for more detail."""

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
                max_output_tokens=500
            )
        )

        answer = response.text
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


def get_conversation_stats() -> Dict:
    """Get statistics about active conversations"""
    cleanup_old_conversations()
    return {
        'active_conversations': len(conversations),
        'total_messages': sum(len(c['messages']) for c in conversations.values())
    }
