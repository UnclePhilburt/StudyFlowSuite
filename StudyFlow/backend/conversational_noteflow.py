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
        import openai

        # Build context from search results
        context_chunks = []
        for result in search_results[:3]:  # Use top 3 results
            text = result.get('content_summary') or result.get('chunk_text', '')
            source = result.get('original_filename', 'Unknown')
            context_chunks.append(f"[From {source}]\n{text}")

        context = "\n\n".join(context_chunks)

        # Build conversation messages for GPT
        messages = [
            {
                "role": "system",
                "content": """You are a helpful study tutor assistant. Students ask you questions about their study materials.

Your job:
1. Answer questions using the provided context from their notes
2. Be conversational and friendly
3. Explain concepts clearly with examples when helpful
4. For follow-up questions like "can you explain more" or "go deeper", expand on the previous topic
5. Always cite which source you're using (e.g., "According to your Biology notes...")
6. If you don't know something, be honest and suggest they upload more notes or rephrase the question

Keep responses concise (2-3 paragraphs max) unless they explicitly ask for more detail."""
            }
        ]

        # Add conversation history (last 6 messages to keep context manageable)
        for msg in conversation_history[-6:]:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Add current question with context
        if context:
            user_message = f"""Question: {question}

Relevant information from my notes:
{context}

Please answer based on this context."""
        else:
            user_message = f"""Question: {question}

I don't have any relevant information in my notes about this. Please let me know."""

        messages.append({
            "role": "user",
            "content": user_message
        })

        debug_log(f"🤖 Generating conversational response with {len(search_results)} context chunks")

        # Call OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective
            messages=messages,
            temperature=0.7,  # Slightly creative but still focused
            max_tokens=500  # Limit response length
        )

        answer = response.choices[0].message.content
        debug_log(f"✅ Generated {len(answer)} character response")

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
