// StudyFlow NoteFlow - Floating Note Search Overlay
console.log('StudyFlow NoteFlow loaded');

const BACKEND_URL = 'https://studyflowsuite.onrender.com';

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
        top: 100px !important;
        right: 20px !important;
        left: auto !important;
        bottom: auto !important;
        width: 380px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        z-index: 2147483647;
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
        padding: 20px;
        max-height: 500px;
        overflow-y: auto;
      }

      .search-box {
        margin-bottom: 16px;
      }

      .search-input-wrapper {
        position: relative;
      }

      .search-input {
        width: 100%;
        padding: 12px 40px 12px 12px;
        border: 2px solid #e2e8f0;
        border-radius: 10px;
        font-size: 14px;
        outline: none;
        transition: border 0.2s;
      }

      .search-input:focus {
        border-color: #667eea;
      }

      .search-input::placeholder {
        color: #94a3b8;
      }

      .search-btn {
        position: absolute;
        right: 6px;
        top: 50%;
        transform: translateY(-50%);
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border: none;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 600;
      }

      .search-btn:hover {
        opacity: 0.9;
      }

      .search-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .results-container {
        min-height: 100px;
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
        font-size: 12px;
        color: #64748b;
        font-style: italic;
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
      <div class="search-box">
        <div class="search-input-wrapper">
          <input
            type="text"
            class="search-input"
            id="note-search-input"
            placeholder="Ask a question about your notes..."
          />
          <button class="search-btn" id="search-btn">Ask</button>
        </div>
      </div>

      <div class="results-container" id="results-container">
        <div class="idle-state">
          <div class="idle-icon">💭</div>
          <div class="idle-text">
            Upload your notes on the StudyFlow website, then ask questions here. I'll search your notes and guide you to the answer!
          </div>
        </div>
      </div>
    </div>
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

    // Dragging
    let isDragging = false;
    let currentX;
    let currentY;
    let initialX;
    let initialY;
    let xOffset = 0;
    let yOffset = 0;

    dragHandle.addEventListener('mousedown', (e) => {
      console.log('🖱️ Mouse down on drag handle');
      initialX = e.clientX - xOffset;
      initialY = e.clientY - yOffset;
      isDragging = true;
      dragHandle.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
      if (isDragging) {
        e.preventDefault();
        currentX = e.clientX - initialX;
        currentY = e.clientY - initialY;
        xOffset = currentX;
        yOffset = currentY;

        overlay.style.transform = `translate(${currentX}px, ${currentY}px)`;
        console.log('📍 Moving:', currentX, currentY);
      }
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        console.log('🖱️ Mouse up - drag ended');
        isDragging = false;
        dragHandle.style.cursor = 'grab';
      }
    });

    dragHandle.style.cursor = 'grab';

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

// Handle search
async function handleSearch() {
  const input = document.getElementById('note-search-input');
  const question = input.value.trim();
  const resultsContainer = document.getElementById('results-container');
  const searchBtn = document.getElementById('search-btn');

  if (!question) {
    return;
  }

  // Show loading state
  searchBtn.disabled = true;
  searchBtn.textContent = '...';
  resultsContainer.innerHTML = `
    <div class="loading-state">
      <div class="loading-spinner"></div>
      <div class="loading-text">Searching your notes...</div>
    </div>
  `;

  try {
    // Get JWT token (check both authToken and jwtToken for compatibility)
    const result = await chrome.storage.local.get(['authToken', 'jwtToken']);
    const token = result.authToken || result.jwtToken;

    if (!token) {
      throw new Error('Not logged in');
    }

    // Call backend to search notes
    const response = await fetch(`${BACKEND_URL}/api/notes/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        question: question
      })
    });

    if (!response.ok) {
      if (response.status === 404) {
        // No notes uploaded
        resultsContainer.innerHTML = `
          <div class="no-notes-warning">
            <div class="no-notes-icon">📚</div>
            <div class="no-notes-text">
              You haven't uploaded any notes yet. Upload your class notes on the StudyFlow website to get started!
            </div>
            <button class="upload-btn" id="upload-notes-btn">Upload Notes</button>
          </div>
        `;
        document.getElementById('upload-notes-btn').addEventListener('click', () => {
          chrome.tabs.create({ url: 'https://unclephilburt.github.io/studyflowwebsite/upload.html' });
        });
        return;
      }
      throw new Error('Failed to search notes');
    }

    const data = await response.json();

    // Display results
    if (data.results && data.results.length > 0) {
      const resultsHTML = data.results.map(result => `
        <div class="result-card">
          <div class="result-source">${result.source}</div>
          <div class="result-text">${result.text}</div>
          <div class="result-hint">💡 ${result.hint}</div>
        </div>
      `).join('');

      resultsContainer.innerHTML = resultsHTML;
    } else {
      resultsContainer.innerHTML = `
        <div class="idle-state">
          <div class="idle-icon">🤷</div>
          <div class="idle-text">
            I couldn't find anything about that in your notes. Try rephrasing your question or upload more notes!
          </div>
        </div>
      `;
    }

  } catch (error) {
    console.error('Search error:', error);
    resultsContainer.innerHTML = `
      <div class="error-state">
        <div class="error-icon">⚠️</div>
        <div class="error-text">
          ${error.message === 'Not logged in' ? 'Please log in to use NoteFlow' : 'Error searching notes. Please try again.'}
        </div>
      </div>
    `;
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = 'Ask';
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
  }
  return true; // Keep message channel open for async response
});

// Log when script loads
console.log('✅ NoteFlow content script loaded and ready');
