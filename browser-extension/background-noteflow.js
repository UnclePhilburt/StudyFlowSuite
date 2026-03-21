// Background service worker for NoteFlow
// Handles API calls to bypass CORS restrictions

const BACKEND_URL = 'https://studyflowsuite.onrender.com';

// Listen for messages from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'searchNotes') {
    handleSearchNotes(request.question, request.conversationId, sendResponse);
    return true; // Keep channel open for async response
  }
});

async function handleSearchNotes(question, conversationId, sendResponse) {
  try {
    // Get auth token from storage
    const result = await chrome.storage.local.get(['authToken', 'jwtToken']);
    const token = result.authToken || result.jwtToken;

    if (!token) {
      sendResponse({
        success: false,
        error: 'Not logged in',
        loginRequired: true
      });
      return;
    }

    // Make API request to conversational chat endpoint (no CORS issues in background worker)
    const requestBody = { message: question };

    // Include conversation_id if this is a follow-up question
    if (conversationId) {
      requestBody.conversation_id = conversationId;
    }

    const response = await fetch(`${BACKEND_URL}/api/notes/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      if (response.status === 404) {
        sendResponse({
          success: false,
          error: 'No notes found',
          noNotes: true
        });
        return;
      }

      if (response.status === 401) {
        sendResponse({
          success: false,
          error: 'Authentication failed',
          loginRequired: true
        });
        return;
      }

      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    // Convert new chat API format to expected format
    sendResponse({
      success: true,
      response: data.response, // AI-generated conversational response
      conversationId: data.conversation_id, // Store for follow-ups
      sources: data.sources || [] // Source citations
    });

  } catch (error) {
    console.error('Background search error:', error);
    sendResponse({
      success: false,
      error: error.message || 'Failed to search notes'
    });
  }
}
