// StudyFlow NoteFlow - Floating Note Search Overlay
console.log('StudyFlow NoteFlow loaded');

const BACKEND_URL = 'https://studyflowsuite.onrender.com';

// Conversation ID for memory across messages
let conversationId = null;

// Create floating overlay window
function createFloatingOverlay() {
  // Check if overlay already exists
  const existing = document.getElementById('studyflow-noteflow');
  if (existing) {
    console.log('⚠️ Overlay already exists, returning existing one');
    return existing;
  }

  console.log('🎨 Creating new overlay...');

  const overlay = document.createElement('div');
  overlay.id = 'studyflow-noteflow';
  overlay.innerHTML = `
    <style>
      #studyflow-noteflow {
        position: fixed !important;
        top: 100px;
        right: 20px;
        left: auto;
        bottom: auto;
        width: 380px;
        height: 600px;
        min-width: 320px;
        max-width: 800px;
        min-height: 400px;
        max-height: 90vh;
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        z-index: 2147483647 !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        overflow: hidden;
      }

      #studyflow-noteflow.minimized {
        height: 60px !important;
      }

      #studyflow-noteflow.minimized .noteflow-body {
        display: none;
      }

      .noteflow-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 16px;
        user-select: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
        touch-action: none;
      }

      .noteflow-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 16px;
        font-weight: 600;
      }

      .noteflow-controls {
        display: flex;
        gap: 8px;
      }

      .noteflow-btn {
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: white;
        width: 28px;
        height: 28px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
      }

      .noteflow-btn:hover {
        background: rgba(255, 255, 255, 0.3);
      }

      .noteflow-body {
        display: flex;
        flex-direction: column;
        height: calc(100% - 60px);
        overflow: hidden;
      }

      .messages-container {
        flex: 1;
        padding: 20px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .input-container {
        padding: 16px 20px;
        border-top: 1px solid #e0e0e0;
        background: white;
        display: flex;
        gap: 8px;
        align-items: center;
      }

      .chat-input {
        flex: 1;
        padding: 12px 16px;
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        font-size: 14px;
        outline: none;
        transition: border-color 0.2s;
      }

      .chat-input:focus {
        border-color: #667eea;
      }

      .chat-input::placeholder {
        color: #94a3b8;
      }

      .send-btn {
        width: 44px;
        height: 44px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        font-size: 18px;
        cursor: pointer;
        transition: opacity 0.2s;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      .send-btn:hover {
        opacity: 0.9;
      }

      .send-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .message-bubble {
        max-width: 85%;
        padding: 12px 16px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.5;
        word-wrap: break-word;
      }

      .message-user {
        align-self: flex-end;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-bottom-right-radius: 4px;
      }

      .message-ai {
        align-self: flex-start;
        background: #f3f4f6;
        color: #1f2937;
        border-bottom-left-radius: 4px;
      }

      .message-loading {
        align-self: flex-start;
        background: #f3f4f6;
        color: #6b7280;
        font-style: italic;
      }

      .idle-state {
        text-align: center;
        padding: 40px 20px;
        color: #64748b;
      }

      .idle-icon {
        font-size: 48px;
        margin-bottom: 12px;
      }

      .idle-text {
        font-size: 13px;
        line-height: 1.6;
      }

      .loading-state {
        text-align: center;
        padding: 40px 20px;
      }

      .loading-spinner {
        width: 40px;
        height: 40px;
        border: 3px solid #e2e8f0;
        border-top-color: #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 16px;
      }

      @keyframes spin {
        to { transform: rotate(360deg); }
      }

      .loading-text {
        font-size: 13px;
        color: #64748b;
      }

      .result-card {
        background: #f8fafc;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        border-left: 3px solid #667eea;
      }

      .result-source {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #667eea;
        font-weight: 600;
        margin-bottom: 8px;
      }

      .result-text {
        font-size: 13px;
        line-height: 1.6;
        color: #334155;
        margin-bottom: 8px;
      }

      .result-hint {
        font-size: 14px;
        line-height: 1.6;
        color: #334155;
      }

      .no-notes-warning {
        background: #fef3c7;
        border: 1px solid #fbbf24;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
      }

      .no-notes-icon {
        font-size: 32px;
        margin-bottom: 8px;
      }

      .no-notes-text {
        font-size: 13px;
        color: #92400e;
        margin-bottom: 12px;
        line-height: 1.5;
      }

      .upload-btn {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
      }

      .upload-btn:hover {
        opacity: 0.9;
      }

      .error-state {
        background: #fee2e2;
        border: 1px solid #ef4444;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
      }

      .error-icon {
        font-size: 32px;
        margin-bottom: 8px;
      }

      .error-text {
        font-size: 13px;
        color: #991b1b;
      }

      .resize-handle {
        position: absolute;
        z-index: 10;
      }

      .resize-handle-right {
        right: 0;
        top: 0;
        width: 8px;
        height: 100%;
        cursor: ew-resize;
      }

      .resize-handle-bottom {
        bottom: 0;
        left: 0;
        width: 100%;
        height: 8px;
        cursor: ns-resize;
      }

      .resize-handle-corner {
        right: 0;
        bottom: 0;
        width: 16px;
        height: 16px;
        cursor: nwse-resize;
        background: rgba(102, 126, 234, 0.1);
        border-radius: 0 0 16px 0;
      }

      .resize-handle-corner::after {
        content: '';
        position: absolute;
        right: 4px;
        bottom: 4px;
        width: 8px;
        height: 8px;
        border-right: 2px solid rgba(102, 126, 234, 0.4);
        border-bottom: 2px solid rgba(102, 126, 234, 0.4);
      }
    </style>

    <div class="noteflow-header" id="noteflow-drag-handle">
      <div class="noteflow-title">
        <span>📝</span>
        <span>NoteFlow</span>
      </div>
      <div class="noteflow-controls">
        <button class="noteflow-btn" id="minimize-btn" title="Minimize">−</button>
        <button class="noteflow-btn" id="close-btn" title="Close">✕</button>
      </div>
    </div>

    <div class="noteflow-body">
      <div class="messages-container" id="messages-container">
        <div class="idle-state">
          <div class="idle-icon">💭</div>
          <div class="idle-text">
            Ask me anything about your notes. I'll remember our conversation!
          </div>
        </div>
      </div>

      <div class="input-container">
        <input
          type="text"
          class="chat-input"
          id="note-search-input"
          placeholder="Ask a question..."
        />
        <button class="send-btn" id="search-btn">
          <span>→</span>
        </button>
      </div>
    </div>

    <div class="resize-handle resize-handle-right"></div>
    <div class="resize-handle resize-handle-bottom"></div>
    <div class="resize-handle resize-handle-corner"></div>
  `;

  document.body.appendChild(overlay);
  console.log('📌 Overlay appended to body');

  // Wait for DOM to settle, then attach all event listeners
  setTimeout(() => {
    const dragHandle = overlay.querySelector('#noteflow-drag-handle');
    const minimizeBtn = overlay.querySelector('#minimize-btn');
    const closeBtn = overlay.querySelector('#close-btn');
    const searchBtn = overlay.querySelector('#search-btn');
    const searchInput = overlay.querySelector('#note-search-input');

    if (!dragHandle) {
      console.error('❌ Drag handle not found!');
      return;
    }

    console.log('✅ All elements found, attaching events...');

    // Dragging variables
    let isDragging = false;
    let currentX;
    let currentY;
    let initialX;
    let initialY;
    let xOffset = 0;
    let yOffset = 0;

    // Resizing variables
    let isResizing = false;
    let resizeDirection = '';
    let startWidth, startHeight, startX, startY;

    dragHandle.addEventListener('mousedown', (e) => {
      console.log('🖱️ Mouse down on drag handle');

      // Get current visual position
      const rect = overlay.getBoundingClientRect();

      // Always use left/top positioning for dragging
      if (overlay.style.left === '' || overlay.style.left === 'auto') {
        // First time dragging - convert from right positioning to left positioning
        overlay.style.left = rect.left + 'px';
        overlay.style.top = rect.top + 'px';
        overlay.style.right = 'auto';
        overlay.style.bottom = 'auto';
        overlay.style.transform = 'none';
      }

      initialX = e.clientX;
      initialY = e.clientY;
      xOffset = parseInt(overlay.style.left, 10);
      yOffset = parseInt(overlay.style.top, 10);

      isDragging = true;
      dragHandle.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
      if (isDragging) {
        e.preventDefault();

        const newX = xOffset + (e.clientX - initialX);
        const newY = yOffset + (e.clientY - initialY);

        overlay.style.left = newX + 'px';
        overlay.style.top = newY + 'px';
        console.log('📍 Moving:', newX, newY);
      }
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        console.log('🖱️ Mouse up - drag ended');
        isDragging = false;
        dragHandle.style.cursor = 'grab';
      }
      if (isResizing) {
        isResizing = false;
        resizeDirection = '';

        // Save size to localStorage
        const width = parseInt(overlay.style.width, 10);
        const height = parseInt(overlay.style.height, 10);
        chrome.storage.local.set({
          noteflowWidth: width,
          noteflowHeight: height
        });
      }
    });

    dragHandle.style.cursor = 'grab';

    // Resizing
    const resizeRight = overlay.querySelector('.resize-handle-right');
    const resizeBottom = overlay.querySelector('.resize-handle-bottom');
    const resizeCorner = overlay.querySelector('.resize-handle-corner');

    // Load saved size from localStorage
    chrome.storage.local.get(['noteflowWidth', 'noteflowHeight'], (result) => {
      if (result.noteflowWidth) {
        overlay.style.width = result.noteflowWidth + 'px';
      }
      if (result.noteflowHeight) {
        overlay.style.height = result.noteflowHeight + 'px';
      }
    });

    function startResize(e, direction) {
      isResizing = true;
      resizeDirection = direction;
      startX = e.clientX;
      startY = e.clientY;

      // Get current dimensions and position
      const rect = overlay.getBoundingClientRect();
      startWidth = rect.width;
      startHeight = rect.height;

      // Get current transform values
      const transform = overlay.style.transform || '';

      // Convert from right/bottom positioning to left/top while preserving visual position
      overlay.style.left = rect.left + 'px';
      overlay.style.top = rect.top + 'px';
      overlay.style.right = 'auto';
      overlay.style.bottom = 'auto';

      // Clear transform since we've converted position
      overlay.style.transform = 'none';

      // Reset drag offsets since position is now in left/top
      xOffset = 0;
      yOffset = 0;

      e.preventDefault();
      e.stopPropagation();
    }

    resizeRight.addEventListener('mousedown', (e) => startResize(e, 'right'));
    resizeBottom.addEventListener('mousedown', (e) => startResize(e, 'bottom'));
    resizeCorner.addEventListener('mousedown', (e) => startResize(e, 'corner'));

    document.addEventListener('mousemove', (e) => {
      if (!isResizing) return;

      e.preventDefault();

      if (resizeDirection === 'right' || resizeDirection === 'corner') {
        const newWidth = startWidth + (e.clientX - startX);
        const minWidth = parseInt(getComputedStyle(overlay).minWidth, 10);
        const maxWidth = parseInt(getComputedStyle(overlay).maxWidth, 10);

        if (newWidth >= minWidth && newWidth <= maxWidth) {
          overlay.style.width = newWidth + 'px';
        }
      }

      if (resizeDirection === 'bottom' || resizeDirection === 'corner') {
        const newHeight = startHeight + (e.clientY - startY);
        const minHeight = parseInt(getComputedStyle(overlay).minHeight, 10);
        const maxHeight = parseInt(getComputedStyle(overlay).maxHeight, 10);

        if (newHeight >= minHeight && newHeight <= maxHeight) {
          overlay.style.height = newHeight + 'px';
        }
      }
    });

    // Minimize button
    minimizeBtn.addEventListener('click', () => {
      overlay.classList.toggle('minimized');
      minimizeBtn.textContent = overlay.classList.contains('minimized') ? '+' : '−';
    });

    // Close button
    closeBtn.addEventListener('click', () => {
      overlay.remove();
    });

    // Search button
    searchBtn.addEventListener('click', handleSearch);

    // Enter key to search
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        handleSearch();
      }
    });

    console.log('✅ All event listeners attached');
  }, 200);

  return overlay;
}

// Add message to chat
function addMessage(content, isUser = false) {
  const messagesContainer = document.getElementById('messages-container');

  // Remove idle state if present
  const idleState = messagesContainer.querySelector('.idle-state');
  if (idleState) {
    idleState.remove();
  }

  const messageBubble = document.createElement('div');
  messageBubble.className = `message-bubble ${isUser ? 'message-user' : 'message-ai'}`;
  messageBubble.textContent = content;

  messagesContainer.appendChild(messageBubble);

  // Scroll to bottom
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  return messageBubble;
}

// Add loading message
function addLoadingMessage() {
  const messagesContainer = document.getElementById('messages-container');

  const loadingBubble = document.createElement('div');
  loadingBubble.className = 'message-bubble message-loading';
  loadingBubble.id = 'loading-message';
  loadingBubble.textContent = 'Thinking...';

  messagesContainer.appendChild(loadingBubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  return loadingBubble;
}

// Remove loading message
function removeLoadingMessage() {
  const loadingMessage = document.getElementById('loading-message');
  if (loadingMessage) {
    loadingMessage.remove();
  }
}

// Handle search
async function handleSearch() {
  const input = document.getElementById('note-search-input');
  const question = input.value.trim();
  const searchBtn = document.getElementById('search-btn');

  if (!question) {
    return;
  }

  // Add user message
  addMessage(question, true);

  // Clear input
  input.value = '';

  // Disable send button and show loading
  searchBtn.disabled = true;
  const loadingBubble = addLoadingMessage();

  try {
    // Send conversational chat request to background worker (bypasses CORS)
    chrome.runtime.sendMessage({
      action: 'searchNotes',
      question: question,
      conversationId: conversationId // Pass existing conversation ID for follow-ups
    }, (response) => {
      // Remove loading message
      removeLoadingMessage();
      searchBtn.disabled = false;

      if (chrome.runtime.lastError) {
        console.error('Message error:', chrome.runtime.lastError);
        const errorMsg = 'Error connecting to extension. Please reload the page.';
        addMessage(errorMsg, false);
        return;
      }

      if (!response.success) {
        let errorMsg = '';

        if (response.loginRequired) {
          errorMsg = '🔒 Please log in to use NoteFlow';
        } else if (response.noNotes) {
          errorMsg = '📚 You haven\'t uploaded any notes yet. Upload your class notes on the StudyFlow website to get started!';
        } else {
          errorMsg = response.error || '⚠️ Error searching notes. Please try again.';
        }

        addMessage(errorMsg, false);
        return;
      }

      // Store conversation ID for follow-up questions
      if (response.conversationId) {
        conversationId = response.conversationId;
        console.log('💬 Conversation ID:', conversationId);
      }

      // Display AI conversational response
      const aiResponse = response.response || 'I couldn\'t find anything about that in your notes. Try rephrasing your question or upload more notes!';

      addMessage(aiResponse, false);

      // Optionally show sources
      if (response.sources && response.sources.length > 0) {
        console.log('📚 Sources:', response.sources);
      }
    });

  } catch (error) {
    console.error('Search error:', error);
    removeLoadingMessage();
    const errorMsg = '⚠️ Error searching notes. Please try again.';
    addMessage(errorMsg, false);
    searchBtn.disabled = false;
  }
}

// Listen for messages from popup to show/hide overlay
// This listener is ALWAYS active, even before page loads
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('📨 Received message:', request.action);

  if (request.action === 'openNoteFlow') {
    console.log('📖 Opening NoteFlow overlay...');
    const overlay = createFloatingOverlay();
    if (overlay) {
      // Remove minimized class if it was minimized
      overlay.classList.remove('minimized');
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Overlay already exists' });
    }
  } else if (request.action === 'closeNoteFlow') {
    console.log('📕 Closing NoteFlow overlay...');
    const overlay = document.getElementById('studyflow-noteflow');
    if (overlay) {
      overlay.remove();
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Overlay not found' });
    }
  } else if (request.action === 'toggleNoteFlow') {
    console.log('🔄 Toggling NoteFlow overlay...');
    const overlay = document.getElementById('studyflow-noteflow');
    if (overlay) {
      // If exists, close it
      overlay.remove();
      sendResponse({ success: true, state: 'closed' });
    } else {
      // If doesn't exist, create it
      createFloatingOverlay();
      sendResponse({ success: true, state: 'opened' });
    }
  } else if (request.action === 'checkNoteFlowState') {
    const overlay = document.getElementById('studyflow-noteflow');
    sendResponse({ isOpen: overlay !== null });
  } else if (request.action === 'syncAuth') {
    // Read auth tokens from website's localStorage
    console.log('🔄 Syncing auth from website localStorage...');
    try {
      const authData = {
        token: localStorage.getItem('token'),
        refreshToken: localStorage.getItem('refreshToken'),
        tokenExpiresAt: localStorage.getItem('tokenExpiresAt'),
        user: localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')) : null
      };
      console.log('✅ Found website auth:', authData.user ? 'logged in' : 'not logged in');
      sendResponse({ success: true, authData });
    } catch (error) {
      console.error('❌ Error reading localStorage:', error);
      sendResponse({ success: false, error: error.message });
    }
  } else if (request.action === 'syncToWebsite') {
    // Write auth tokens to website's localStorage
    console.log('🔄 Syncing auth from extension to website localStorage...');
    try {
      if (request.authData) {
        localStorage.setItem('token', request.authData.token);
        localStorage.setItem('refreshToken', request.authData.refreshToken);
        localStorage.setItem('tokenExpiresAt', request.authData.tokenExpiresAt);
        localStorage.setItem('user', JSON.stringify(request.authData.user));
        console.log('✅ Synced extension auth to website');
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, error: 'No auth data provided' });
      }
    } catch (error) {
      console.error('❌ Error writing to localStorage:', error);
      sendResponse({ success: false, error: error.message });
    }
  }
  return true; // Keep message channel open for async response
});

// Log when script loads
console.log('✅ NoteFlow content script loaded and ready');
