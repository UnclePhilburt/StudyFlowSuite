# Conversational NoteFlow Chat

## Overview

Added AI-powered conversational chat to NoteFlow that remembers context and allows students to have back-and-forth discussions about their study materials.

## What Changed

### Before (Simple Search)
```
Student: "How does DNA replicate?"
→ Returns raw search results with hints

Student: "Can you explain more?"
→ Searches for "explain more" (fails - no context)
```

### After (Conversational AI)
```
Student: "How does DNA replicate?"
→ AI: "DNA replicates through semiconservative replication where..."

Student: "Can you explain more?"
→ AI: "Sure! Let me go deeper into DNA replication..." (remembers context)

Student: "What enzymes are involved?"
→ AI: "In DNA replication, the key enzymes include..." (still in context)
```

## New Files

1. **`StudyFlow/backend/conversational_noteflow.py`**
   - Conversation memory management
   - AI response generation with GPT-4o-mini
   - Auto-cleanup of old conversations (1 hour)

2. **`StudyFlow/backend/app.py`** (updated)
   - New endpoint: `POST /api/notes/chat`
   - Uses existing search infrastructure
   - Maintains conversation history

## API Endpoint

### `POST /api/notes/chat`

**Request:**
```json
{
  "message": "How does DNA replicate?",
  "conversation_id": "optional-uuid"  // omit for new conversation
}
```

**Response:**
```json
{
  "conversation_id": "abc-123-def",
  "response": "DNA replicates through semiconservative replication where each strand serves as a template...",
  "sources": [
    {
      "filename": "DNA.txt (Wikipedia - Biology)",
      "similarity": 0.89
    }
  ]
}
```

## How It Works

1. **New Conversation:** Student asks first question
   - System creates conversation ID
   - Searches database for relevant chunks
   - Generates AI response with context
   - Returns conversation ID

2. **Follow-up Questions:** Student asks "can you explain more?"
   - Includes conversation ID in request
   - System loads conversation history
   - AI understands this is a follow-up
   - Expands on previous answer

3. **Memory Management:**
   - Conversations stored in memory (1 hour)
   - Auto-cleanup of old conversations
   - Last 6 messages used for context (prevents token overflow)

## Features

✅ **Context-Aware:** Understands follow-up questions
✅ **Cites Sources:** Shows which notes were used
✅ **Conversational:** Friendly tutor tone
✅ **Cost-Effective:** Uses GPT-4o-mini ($0.15 per 1M tokens)
✅ **Auto-Cleanup:** Old conversations deleted after 1 hour

## Deployment

This is a **backend change** that requires deployment to Render.

### Steps:
1. ✅ Code changes complete
2. ⚠️ **Push to GitHub** (triggers Render deployment)
3. ⏳ Wait for deployment (~3 minutes)
4. ✅ Test with `test_conversational_chat.py`

### Important:
This modifies the backend API, so **you need to push to GitHub** to deploy to Render.

## Frontend Integration

To use this in your frontend (future work):

**Old Code (Search):**
```javascript
fetch('/api/notes/search', {
  method: 'POST',
  body: JSON.stringify({ question: "How does DNA work?" })
})
```

**New Code (Chat):**
```javascript
// Start conversation
let conversationId = null;

// First message
fetch('/api/notes/chat', {
  method: 'POST',
  body: JSON.stringify({
    message: "How does DNA work?"
  })
}).then(r => r.json()).then(data => {
  conversationId = data.conversation_id;
  displayResponse(data.response);
});

// Follow-up
fetch('/api/notes/chat', {
  method: 'POST',
  body: JSON.stringify({
    message: "Can you explain more?",
    conversation_id: conversationId
  })
}).then(r => r.json()).then(data => {
  displayResponse(data.response);
});
```

## Cost Analysis

**Old System (Hints):**
- 1 embedding: $0.00002
- 1 Gemini hint: $0.0001
- **Total per search: ~$0.00012**

**New System (Chat):**
- 1 embedding: $0.00002
- 1 GPT-4o-mini response: $0.00015 (avg)
- **Total per message: ~$0.00017**

Minimal increase (~$0.05 per 1000 messages)

## Testing

1. **Deploy to Render:**
   ```bash
   git add .
   git commit -m "Add conversational chat to NoteFlow"
   git push origin main
   ```

2. **Get JWT Token:**
   - Login to StudyFlow
   - Open DevTools → Application → Local Storage
   - Copy JWT token

3. **Run Test:**
   ```bash
   python test_conversational_chat.py
   ```

## Limitations

1. **Memory:** Conversations stored in-memory (lost on server restart)
   - For production: Use Redis or database storage

2. **Multi-Server:** Won't work across multiple Render instances
   - For scaling: Use Redis or session store

3. **1 Hour Timeout:** Conversations auto-deleted after 1 hour
   - Can be extended if needed

## Next Steps

- [ ] Deploy to Render (push to GitHub)
- [ ] Test with Wikipedia articles
- [ ] Update frontend to use chat endpoint
- [ ] (Optional) Add Redis for persistent storage
- [ ] (Optional) Add conversation export feature
