// Background service worker for NoteFlow
// Handles API calls to bypass CORS restrictions

const BACKEND_URL = 'https://studyflowsuite.onrender.com';

// Listen for messages from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'searchNotes') {
    handleSearchNotes(request.question, sendResponse);
    return true; // Keep channel open for async response
  }
});

async function handleSearchNotes(question, sendResponse) {
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

    // Make API request (no CORS issues in background worker)
    const response = await fetch(`${BACKEND_URL}/api/notes/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ question })
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

    sendResponse({
      success: true,
      results: data.results || []
    });

  } catch (error) {
    console.error('Background search error:', error);
    sendResponse({
      success: false,
      error: error.message || 'Failed to search notes'
    });
  }
}
