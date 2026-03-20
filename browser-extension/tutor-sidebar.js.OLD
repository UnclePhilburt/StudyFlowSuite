// StudyFlow AI Tutor - Legal Tutoring Sidebar
// Passively detects questions and shows step-by-step explanations
// Student must manually click answers (Human-in-the-loop)

console.log('StudyFlow AI Tutor loaded');

const BACKEND_URL = 'https://studyflowsuite.onrender.com';

// Create sidebar UI
function createTutorSidebar() {
  // Check if sidebar already exists
  if (document.getElementById('studyflow-tutor-sidebar')) {
    return;
  }

  const sidebar = document.createElement('div');
  sidebar.id = 'studyflow-tutor-sidebar';
  sidebar.innerHTML = `
    <style>
      #studyflow-tutor-sidebar {
        position: fixed;
        top: 0;
        right: -400px;
        width: 400px;
        height: 100vh;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
        z-index: 999999;
        transition: right 0.3s ease;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        display: flex;
        flex-direction: column;
      }

      #studyflow-tutor-sidebar.open {
        right: 0;
      }

      .sidebar-header {
        background: rgba(255, 255, 255, 0.15);
        padding: 20px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.2);
      }

      .sidebar-title {
        color: white;
        font-size: 20px;
        font-weight: 700;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .sidebar-subtitle {
        color: rgba(255, 255, 255, 0.8);
        font-size: 12px;
        margin-top: 5px;
      }

      .sidebar-content {
        flex: 1;
        overflow-y: auto;
        padding: 20px;
        color: white;
      }

      .concept-box {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
        border-left: 4px solid #00c853;
      }

      .concept-label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
        opacity: 0.8;
        margin-bottom: 8px;
      }

      .concept-text {
        font-size: 15px;
        font-weight: 600;
        line-height: 1.4;
      }

      .explanation-box {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 12px;
        padding: 20px;
        color: #1e293b;
        line-height: 1.6;
      }

      .explanation-step {
        margin-bottom: 16px;
        padding-left: 28px;
        position: relative;
      }

      .explanation-step::before {
        content: attr(data-step);
        position: absolute;
        left: 0;
        top: 0;
        width: 20px;
        height: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
      }

      .explanation-step-text {
        font-size: 14px;
        color: #334155;
      }

      .loading-state {
        text-align: center;
        padding: 40px 20px;
      }

      .loading-spinner {
        width: 40px;
        height: 40px;
        border: 3px solid rgba(255, 255, 255, 0.3);
        border-top-color: white;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 16px;
      }

      @keyframes spin {
        to { transform: rotate(360deg); }
      }

      .toggle-button {
        position: fixed;
        top: 50%;
        right: 0;
        transform: translateY(-50%);
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 16px 12px;
        cursor: pointer;
        font-size: 20px;
        border-radius: 8px 0 0 8px;
        box-shadow: -2px 2px 10px rgba(0, 0, 0, 0.2);
        z-index: 999998;
        transition: all 0.3s ease;
      }

      .toggle-button:hover {
        padding-right: 16px;
      }

      .engagement-tracker {
        background: rgba(255, 255, 255, 0.1);
        padding: 12px;
        border-radius: 8px;
        margin-top: 16px;
        font-size: 12px;
        text-align: center;
      }

      .idle-state {
        text-align: center;
        padding: 40px 20px;
        opacity: 0.8;
      }

      .idle-icon {
        font-size: 48px;
        margin-bottom: 16px;
      }

      .idle-text {
        font-size: 14px;
        line-height: 1.6;
      }
    </style>

    <button class="toggle-button" id="sidebar-toggle">🤖</button>

    <div class="sidebar-header">
      <h2 class="sidebar-title">
        <span>🧠</span>
        <span>AI Tutor</span>
      </h2>
      <div class="sidebar-subtitle">Legal cognitive support tool</div>
    </div>

    <div class="sidebar-content" id="sidebar-content">
      <div class="idle-state">
        <div class="idle-icon">📚</div>
        <div class="idle-text">
          Navigate to a quiz question and I'll provide step-by-step explanations to help you understand the concept.
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(sidebar);

  // Toggle button functionality
  const toggleBtn = document.getElementById('sidebar-toggle');
  toggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    toggleBtn.textContent = sidebar.classList.contains('open') ? '✖' : '🤖';
  });

  return sidebar;
}

// Show explanation in sidebar
function showExplanation(questionText, explanation) {
  const content = document.getElementById('sidebar-content');
  const sidebar = document.getElementById('studyflow-tutor-sidebar');

  if (!content || !sidebar) return;

  // Parse explanation into steps (assuming backend returns numbered steps)
  const steps = explanation.split(/\d+\.\s+/).filter(s => s.trim());

  const stepsHTML = steps.map((step, index) => `
    <div class="explanation-step" data-step="${index + 1}">
      <div class="explanation-step-text">${step.trim()}</div>
    </div>
  `).join('');

  content.innerHTML = `
    <div class="concept-box">
      <div class="concept-label">Question</div>
      <div class="concept-text">${questionText.substring(0, 150)}...</div>
    </div>

    <div class="explanation-box">
      ${stepsHTML}
    </div>

    <div class="engagement-tracker">
      ✅ Explanation viewed • Read time tracked for compliance
    </div>
  `;

  // Auto-open sidebar
  sidebar.classList.add('open');
  document.getElementById('sidebar-toggle').textContent = '✖';

  // Track engagement (time spent reading)
  const startTime = Date.now();
  window.addEventListener('beforeunload', () => {
    const readTime = Math.floor((Date.now() - startTime) / 1000);
    console.log(`📊 Student read explanation for ${readTime} seconds`);
    // TODO: Send engagement data to backend for compliance tracking
  });
}

// Show loading state
function showLoading() {
  const content = document.getElementById('sidebar-content');
  if (!content) return;

  content.innerHTML = `
    <div class="loading-state">
      <div class="loading-spinner"></div>
      <div>Generating step-by-step explanation...</div>
    </div>
  `;
}

// Passive question detection (no automation)
let lastDetectedQuestion = '';
let detectionInterval = null;

async function detectAndExplain() {
  // Simple detection: look for question text on page
  const questionSelectors = [
    '.question-text',
    '[class*="question"]',
    '[data-automation="sdk-take-item-question"]',
    '.assessment-question',
    '.quiz-question'
  ];

  let questionText = '';

  for (const selector of questionSelectors) {
    const element = document.querySelector(selector);
    if (element && element.textContent.trim().length > 20) {
      questionText = element.textContent.trim();
      break;
    }
  }

  // If we found a new question, get explanation
  if (questionText && questionText !== lastDetectedQuestion && questionText.includes('?')) {
    lastDetectedQuestion = questionText;
    console.log('📖 New question detected, fetching explanation...');

    showLoading();

    try {
      // Get JWT token
      const result = await chrome.storage.local.get(['jwtToken']);
      const token = result.jwtToken;

      if (!token) {
        throw new Error('Not logged in');
      }

      // Call backend for explanation (not answer)
      const response = await fetch(`${BACKEND_URL}/api/tutor/explain`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          question: questionText
        })
      });

      if (!response.ok) {
        throw new Error('Failed to get explanation');
      }

      const data = await response.json();
      showExplanation(questionText, data.explanation);

    } catch (error) {
      console.error('Error fetching explanation:', error);
      const content = document.getElementById('sidebar-content');
      if (content) {
        content.innerHTML = `
          <div class="idle-state">
            <div class="idle-icon">⚠️</div>
            <div class="idle-text">
              Error: ${error.message}<br><br>
              Please make sure you're logged in.
            </div>
          </div>
        `;
      }
    }
  }
}

// Initialize
function init() {
  // Create sidebar UI
  createTutorSidebar();

  // Start passive detection (check every 3 seconds)
  detectionInterval = setInterval(detectAndExplain, 3000);

  console.log('✅ StudyFlow AI Tutor initialized (Legal mode)');
}

// Wait for page to load, then initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
