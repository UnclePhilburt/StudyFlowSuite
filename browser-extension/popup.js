// Popup script - Progressive setup wizard + quiz control

console.log('popup.js loaded!');

let statusInterval = null;
let lastQuestionCount = 0;
let lastErrorCount = 0;

// Utility function to check user tier
function getUserTier(user) {
  if (!user) return 'free';

  // Beta testers (grandfathered) get Pro features
  if (user.is_beta) return 'beta';

  // Pro/trialing users
  if (user.subscription_status === 'active' || user.subscription_status === 'trialing') {
    return 'pro';
  }

  return 'free';
}

// Lock Pro features for free users
function lockProFeatures(isPro) {
  const questionLimitInput = document.getElementById('totalQuestions');
  const targetTimeInput = document.getElementById('targetTime');

  if (!isPro) {
    // Disable pro settings
    questionLimitInput.disabled = true;
    targetTimeInput.disabled = true;

    // Add placeholder text indicating Pro feature
    questionLimitInput.placeholder = 'Pro Only';
    targetTimeInput.placeholder = 'Pro Only';

    // Add visual styling to show locked
    questionLimitInput.style.opacity = '0.5';
    targetTimeInput.style.opacity = '0.5';
    questionLimitInput.style.cursor = 'not-allowed';
    targetTimeInput.style.cursor = 'not-allowed';
  } else {
    // Enable pro settings
    questionLimitInput.disabled = false;
    targetTimeInput.disabled = false;

    // Restore normal placeholders
    questionLimitInput.placeholder = 'Unlimited';
    targetTimeInput.placeholder = 'Auto pace';

    // Remove locked styling
    questionLimitInput.style.opacity = '1';
    targetTimeInput.style.opacity = '1';
    questionLimitInput.style.cursor = 'text';
    targetTimeInput.style.cursor = 'text';
  }
}

// Initialize user profile
async function initUserProfile() {
  let user = await window.auth.getCurrentUser();

  if (user) {
    // Fetch latest user data from server to sync subscription status
    try {
      const token = await window.auth.getAuthToken();
      const response = await fetch('https://studyflowsuite.onrender.com/api/me', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const freshUserData = await response.json();
        // Update cached user data with fresh subscription status
        user = freshUserData;
        await chrome.storage.local.set({ user: freshUserData });
      }
    } catch (error) {
      console.log('Could not refresh user data:', error);
      // Continue with cached data
    }

    // Set user avatar (first letter of name or email)
    const initial = (user.name || user.email).charAt(0).toUpperCase();
    document.getElementById('userAvatar').textContent = initial;

    // Set user name
    document.getElementById('userName').textContent = user.name || user.email;

    // Get user tier
    const tier = getUserTier(user);
    const isPro = tier === 'pro' || tier === 'beta';

    // Set user plan
    let planText = 'Free Plan';
    if (tier === 'beta') {
      planText = 'Beta (Pro)';
    } else if (tier === 'pro') {
      planText = 'Pro Plan';
    }
    document.getElementById('userPlan').textContent = planText;

    // Lock Pro features for free users
    lockProFeatures(isPro);

    // Restrict AI model selection based on subscription
    const aiModelSelect = document.getElementById('aiModel');
    const advancedOption = aiModelSelect.querySelector('option[value="gpt-4o"]');
    const modelHint = document.getElementById('modelHint');

    if (!isPro) {
      // Free user - disable advanced model
      advancedOption.disabled = true;
      aiModelSelect.value = 'gpt-4o-mini'; // Force basic model
      modelHint.textContent = 'Upgrade to Pro to unlock Advanced Model';
      modelHint.style.color = '#94a3b8';
    } else {
      // Pro user - enable all models
      advancedOption.disabled = false;
      modelHint.textContent = 'Basic: Fast & accurate • Advanced: Maximum accuracy';
      modelHint.style.color = '#94a3b8';
    }

    // Check if we should show welcome animation
    const result = await chrome.storage.local.get(['showWelcome']);
    if (result.showWelcome) {
      showWelcomeAnimation(user.name || user.email.split('@')[0]);
      // Clear the flag
      await chrome.storage.local.remove(['showWelcome']);
    }
  }
}

// Show welcome animation
function showWelcomeAnimation(name) {
  // Create welcome overlay
  const overlay = document.createElement('div');
  overlay.className = 'welcome-overlay';
  overlay.innerHTML = `
    <div class="welcome-content">
      <div class="welcome-title">Hello!</div>
      <div class="welcome-name">${name}</div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Remove overlay after animation
  setTimeout(() => {
    overlay.remove();
  }, 2500);
}

// Handle logout
document.getElementById('logoutBtn').addEventListener('click', () => {
  if (confirm('Are you sure you want to logout?')) {
    window.auth.logout();
  }
});

// Prevent free users from selecting advanced model
document.getElementById('aiModel').addEventListener('change', async (e) => {
  const user = await window.auth.getCurrentUser();
  const isPro = user && (user.subscription_status === 'active' || user.subscription_status === 'trialing');

  if (!isPro && e.target.value === 'gpt-4o') {
    // Revert to basic model
    e.target.value = 'gpt-4o-mini';
    alert('Advanced Model is only available for Pro users. Upgrade to unlock!');
  }
});

// Add click handlers for locked Pro features
document.getElementById('totalQuestions').addEventListener('click', async (e) => {
  const user = await window.auth.getCurrentUser();
  const tier = getUserTier(user);
  const isPro = tier === 'pro' || tier === 'beta';

  if (!isPro) {
    alert('Question Limit is a Pro feature. Upgrade to Pro for unlimited questions and advanced controls!\n\nVisit: https://unclephilburt.github.io/studyflowwebsite/');
  }
});

document.getElementById('targetTime').addEventListener('click', async (e) => {
  const user = await window.auth.getCurrentUser();
  const tier = getUserTier(user);
  const isPro = tier === 'pro' || tier === 'beta';

  if (!isPro) {
    alert('Target Time is a Pro feature. Upgrade to Pro for unlimited questions and advanced controls!\n\nVisit: https://unclephilburt.github.io/studyflowwebsite/');
  }
});

// Initialize on page load
initUserProfile();

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
      content.classList.add('hidden');
    });
    document.getElementById(`${tab}-tab`).classList.remove('hidden');

    // Load stats if switching to stats tab
    if (tab === 'stats') {
      loadStats();
    }
  });
});

// Load stats from API
async function loadStats() {
  try {
    const token = await window.auth.getAuthToken();
    const response = await fetch('https://studyflowsuite.onrender.com/api/stats', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (response.ok) {
      const data = await response.json();
      displayStats(data);
    } else {
      console.error('Failed to load stats:', response.status);
      displayStatsError();
    }
  } catch (error) {
    console.error('Error loading stats:', error);
    displayStatsError();
  }
}

// Display stats in UI
function displayStats(data) {
  // Update stat cards
  document.getElementById('totalQuestions').textContent = data.stats.total_questions.toLocaleString();
  document.getElementById('questionsToday').textContent = data.stats.questions_today.toLocaleString();
  document.getElementById('questionsWeek').textContent = data.stats.questions_this_week.toLocaleString();
  document.getElementById('accountTier').textContent = data.user.tier;

  // Update question types
  const questionTypesDiv = document.getElementById('questionTypes');
  if (data.question_types && Object.keys(data.question_types).length > 0) {
    questionTypesDiv.innerHTML = '';
    for (const [type, count] of Object.entries(data.question_types)) {
      const row = document.createElement('div');
      row.className = 'type-row';
      row.innerHTML = `
        <span class="type-name">${type}</span>
        <span class="type-count">${count.toLocaleString()}</span>
      `;
      questionTypesDiv.appendChild(row);
    }
  } else {
    questionTypesDiv.innerHTML = '<div class="loading-spinner">No questions yet</div>';
  }

  // Update account info
  document.getElementById('userEmail').textContent = data.user.email;

  if (data.user.created_at) {
    const createdDate = new Date(data.user.created_at);
    document.getElementById('memberSince').textContent = createdDate.toLocaleDateString();
  }

  if (data.stats.last_activity) {
    const lastActivityDate = new Date(data.stats.last_activity);
    const now = new Date();
    const diffMs = now - lastActivityDate;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    let lastActivityText = '';
    if (diffMins < 1) {
      lastActivityText = 'Just now';
    } else if (diffMins < 60) {
      lastActivityText = `${diffMins} min ago`;
    } else if (diffHours < 24) {
      lastActivityText = `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    } else {
      lastActivityText = `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    }

    document.getElementById('lastActivity').textContent = lastActivityText;
  } else {
    document.getElementById('lastActivity').textContent = 'No activity yet';
  }
}

// Display error message
function displayStatsError() {
  document.getElementById('totalQuestions').textContent = 'Error';
  document.getElementById('questionsToday').textContent = 'Error';
  document.getElementById('questionsWeek').textContent = 'Error';
  document.getElementById('accountTier').textContent = 'Error';
  document.getElementById('questionTypes').innerHTML = '<div class="loading-spinner">Failed to load</div>';
}

// Refresh stats button
document.getElementById('refreshStats').addEventListener('click', () => {
  loadStats();
});

// Settings validation
document.getElementById('totalQuestions').addEventListener('input', (e) => {
  const totalQuestions = parseInt(e.target.value);
  const targetTimeInput = document.getElementById('targetTime');

  if (!totalQuestions || totalQuestions <= 0) {
    // Disable target time if no total questions
    targetTimeInput.disabled = true;
    targetTimeInput.value = '';
  } else {
    targetTimeInput.disabled = false;
  }
});

// Start button - triggers progressive setup or starts quiz
document.getElementById('startBtn').addEventListener('click', async () => {
  console.log('Start button clicked!');
  await checkAndStartSetup();
});

// Resume button
document.getElementById('resumeBtn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'resume' }, (response) => {
    if (response.success) {
      document.getElementById('resumeBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      updateStatus('Assistant resumed!', 'running');
    }
  });
});

// Stop button
document.getElementById('stopBtn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'stop' }, (response) => {
    if (response.success) {
      document.getElementById('startBtn').classList.remove('hidden');
      document.getElementById('resumeBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.add('hidden');
      updateStatus('Assistant stopped', 'idle');
      stopStatusPolling();
    }
  });
});


async function checkAndStartSetup() {
  console.log('checkAndStartSetup called');
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // All modes now skip setup wizard and auto-detect questions
  console.log('Starting assistant...');
  startQuizMode(tab.id);
}


function startQuizMode(tabId) {
  // Get settings
  const totalQuestions = parseInt(document.getElementById('totalQuestions').value) || null;
  const targetTime = parseInt(document.getElementById('targetTime').value) || null;
  const quizMode = document.getElementById('quizMode').value;
  const aiModel = document.getElementById('aiModel').value;

  // Send to background with settings
  chrome.runtime.sendMessage({
    action: 'start',
    tabId: tabId,
    settings: {
      totalQuestions: totalQuestions,
      targetTime: targetTime,
      answerMode: quizMode,
      onePageMode: quizMode === 'single-page' || quizMode === 'multi-question',
      aiModel: aiModel
    }
  }, (response) => {
    if (response.success) {
      document.getElementById('startBtn').classList.add('hidden');
      document.getElementById('resumeBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      document.getElementById('startBtn').innerHTML = '<span>▶</span><span>Start Assistant</span>';
      updateStatus('Assistant started!', 'running');
    }
  });

  startStatusPolling();
}

function startStatusPolling() {
  statusInterval = setInterval(() => {
    chrome.runtime.sendMessage({ action: 'getStatus' }, (status) => {
      if (status) {
        // Check if waiting for navigation
        if (status.waitingForNavigation) {
          updateStatus('✅ Page complete! Click Next/Submit, then Resume', 'success');
          document.getElementById('resumeBtn').classList.remove('hidden');
          document.getElementById('stopBtn').classList.remove('hidden');
          document.getElementById('startBtn').classList.add('hidden');
        } else if (status.isRunning && !status.isPaused) {
          // Running normally - ensure stop button is visible
          document.getElementById('resumeBtn').classList.add('hidden');
          document.getElementById('stopBtn').classList.remove('hidden');
          document.getElementById('startBtn').classList.add('hidden');
        } else if (!status.isRunning) {
          // Not running - show start button
          document.getElementById('startBtn').classList.remove('hidden');
          document.getElementById('resumeBtn').classList.add('hidden');
          document.getElementById('stopBtn').classList.add('hidden');
        }
      }
    });
  }, 1000);
}

function stopStatusPolling() {
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
}

function updateStatus(message, type) {
  // Just log status updates since we removed the status bar UI
  console.log(`Status [${type}]: ${message}`);
}


// Check if already running on popup open, or check setup progress
chrome.runtime.sendMessage({ action: 'getStatus' }, async (status) => {
  if (status && status.isRunning) {
    document.getElementById('startBtn').classList.add('hidden');

    if (status.waitingForNavigation) {
      // Show resume button
      document.getElementById('resumeBtn').classList.remove('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      updateStatus('✅ Page complete! Click Next/Submit, then Resume', 'success');
    } else {
      // Normal running state
      document.getElementById('stopBtn').classList.remove('hidden');
      updateStatus('Assistant running', 'running');
    }

    startStatusPolling();
  } else {
    // Not running - ready to start
    updateStatus('Click "Start Assistant" to begin', 'idle');
  }
});

// Cleanup on popup close
window.addEventListener('unload', () => {
  stopStatusPolling();
});

// Dev Inspector removed for production build
