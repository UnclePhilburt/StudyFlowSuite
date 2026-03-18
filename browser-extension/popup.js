// Popup script - Progressive setup wizard + quiz control

let statusInterval = null;
let lastQuestionCount = 0;
let lastErrorCount = 0;
let setupData = {
  questionSelector: null,
  answersSelector: null,
  submitSelector: null
};

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

    // Set user plan
    const planText = user.subscription_status === 'active' || user.subscription_status === 'trialing' ? 'Pro Plan' : 'Free Plan';
    document.getElementById('userPlan').textContent = planText;

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

// Initialize on page load
initUserProfile();

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
  await checkAndStartSetup();
});

// Resume button
document.getElementById('resumeBtn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'resume' }, (response) => {
    if (response.success) {
      document.getElementById('resumeBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      updateStatus('Quiz resumed!', 'running');
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
      updateStatus('Quiz stopped', 'idle');
      stopStatusPolling();
    }
  });
});

// Clear setup button
document.getElementById('clearSetup').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = new URL(tab.url);
  const domain = url.hostname;

  chrome.storage.local.get(['siteSetups'], (result) => {
    const setups = result.siteSetups || {};
    delete setups[domain];
    chrome.storage.local.set({ siteSetups: setups }, () => {
      updateStatus('✓ Saved setup cleared for this site', 'success');
      document.getElementById('startBtn').innerHTML = '<span>▶</span> Start Quiz';
      setTimeout(() => {
        updateStatus('Click "Start Quiz" to begin', 'idle');
      }, 2000);
    });
  });
});

async function checkAndStartSetup() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = new URL(tab.url);
  const domain = url.hostname;

  // Check if one-page mode is enabled - skip setup wizard if it is
  const onePageMode = document.getElementById('onePageMode').checked;
  if (onePageMode) {
    console.log('One-page mode enabled - skipping setup wizard');
    startQuizMode(tab.id);
    return;
  }

  // Check current setup progress
  chrome.storage.local.get(['siteSetups'], async (result) => {
    const setups = result.siteSetups || {};
    let savedSetup = setups[domain] || { questionSelector: null, answersSelector: null, submitSelector: null };

    setupData = savedSetup;

    // Determine next step
    if (!savedSetup.questionSelector) {
      // Step 1: Select question
      updateStatus('Step 1/3: Click on the question text on the page', 'running');
      document.getElementById('startBtn').innerHTML = '<span>📝</span> Click Question on Page';
      await startElementPicker('question');
    } else if (!savedSetup.answersSelector) {
      // Step 2: Select answers
      updateStatus('Step 2/3: Click on the answer area on the page', 'running');
      document.getElementById('startBtn').innerHTML = '<span>☑️</span> Click Answers on Page';
      await startElementPicker('answers');
    } else if (!savedSetup.submitSelector) {
      // Step 3: Select submit button
      updateStatus('Step 3/3: Click the submit button on the page', 'running');
      document.getElementById('startBtn').innerHTML = '<span>▶️</span> Click Submit on Page';
      await startElementPicker('submit');
    } else {
      // All setup complete - start quiz!
      startQuizMode(tab.id);
    }
  });
}

async function startElementPicker(mode) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Start picker in content script
  chrome.tabs.sendMessage(tab.id, { action: 'startPicker', mode });
}

function startQuizMode(tabId) {
  // Get settings
  const totalQuestions = parseInt(document.getElementById('totalQuestions').value) || null;
  const targetTime = parseInt(document.getElementById('targetTime').value) || null;
  const onePageMode = document.getElementById('onePageMode').checked;
  const aiModel = document.getElementById('aiModel').value;

  // Send to background with settings
  chrome.runtime.sendMessage({
    action: 'start',
    tabId: tabId,
    settings: {
      totalQuestions: totalQuestions,
      targetTime: targetTime,
      onePageMode: onePageMode,
      aiModel: aiModel
    }
  }, (response) => {
    if (response.success) {
      document.getElementById('startBtn').classList.add('hidden');
      document.getElementById('resumeBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      document.getElementById('startBtn').innerHTML = '<span>▶</span> Start Quiz';
      updateStatus('Quiz mode started!', 'running');
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
        } else if (status.isRunning && !status.isPaused) {
          // Running normally
          if (document.getElementById('resumeBtn').classList.contains('hidden') === false) {
            // Just resumed
            document.getElementById('resumeBtn').classList.add('hidden');
          }
        }

        // Animate question count if changed
        if (status.questionCount !== lastQuestionCount) {
          const questionEl = document.getElementById('questionCount');
          questionEl.classList.add('counting');
          questionEl.textContent = status.questionCount;
          setTimeout(() => questionEl.classList.remove('counting'), 600);
          lastQuestionCount = status.questionCount;
        }

        // Animate error count if changed
        if (status.errorCount !== lastErrorCount) {
          const errorEl = document.getElementById('errorCount');
          errorEl.classList.add('counting');
          errorEl.textContent = status.errorCount;
          setTimeout(() => errorEl.classList.remove('counting'), 600);
          lastErrorCount = status.errorCount;
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
  const statusText = document.getElementById('statusText');
  const statusDot = document.getElementById('statusDot');

  statusText.textContent = message;

  // Update status dot
  statusDot.className = 'status-dot';
  if (type === 'running') {
    statusDot.classList.add('running');
  } else if (type === 'idle') {
    statusDot.classList.add('idle');
  } else if (type === 'success') {
    // Keep green animated for success
  } else {
    statusDot.classList.add('idle');
  }
}

// Listen for element selection from content script
chrome.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  if (request.action === 'elementSelected') {
    const { mode, selector, preview } = request;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = new URL(tab.url);
    const domain = url.hostname;

    // Save to setup data
    if (mode === 'question') {
      setupData.questionSelector = selector;
      updateStatus('✓ Question saved! Auto-continuing...', 'success');
    } else if (mode === 'answers') {
      setupData.answersSelector = selector;
      updateStatus('✓ Answers saved! Auto-continuing...', 'success');
    } else if (mode === 'submit') {
      setupData.submitSelector = selector;
      updateStatus('✓ Submit button saved! Starting quiz...', 'success');
    }

    document.getElementById('startBtn').innerHTML = '<span>▶</span> Start Quiz';

    // Save to storage
    chrome.storage.local.get(['siteSetups'], (result) => {
      const setups = result.siteSetups || {};
      setups[domain] = setupData;
      chrome.storage.local.set({ siteSetups: setups }, () => {
        console.log('Setup saved for', domain, setupData);

        // Auto-advance to next step after 1 second
        setTimeout(() => {
          checkAndStartSetup();
        }, 1000);
      });
    });
  } else if (request.action === 'pickerCancelled') {
    // User cancelled - reset button
    document.getElementById('startBtn').innerHTML = '<span>▶</span> Start Quiz';
    updateStatus('Setup cancelled. Click Start Quiz to continue.', 'idle');
  }
});

// Check if already running on popup open, or check setup progress
chrome.runtime.sendMessage({ action: 'getStatus' }, async (status) => {
  if (status && status.isRunning) {
    document.getElementById('startBtn').classList.add('hidden');
    document.getElementById('questionCount').textContent = status.questionCount;
    document.getElementById('errorCount').textContent = status.errorCount;

    if (status.waitingForNavigation) {
      // Show resume button
      document.getElementById('resumeBtn').classList.remove('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      updateStatus('✅ Page complete! Click Next/Submit, then Resume', 'success');
    } else {
      // Normal running state
      document.getElementById('stopBtn').classList.remove('hidden');
      updateStatus('Quiz mode running', 'running');
    }

    startStatusPolling();
  } else {
    // Check setup progress for current site
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = new URL(tab.url);
    const domain = url.hostname;

    chrome.storage.local.get(['siteSetups'], (result) => {
      const setups = result.siteSetups || {};
      const savedSetup = setups[domain];

      if (!savedSetup || !savedSetup.questionSelector) {
        updateStatus('Click "Start Quiz" to set up this site', 'idle');
      } else if (!savedSetup.answersSelector) {
        updateStatus('Setup 1/3 complete. Click to continue', 'idle');
        document.getElementById('startBtn').innerHTML = '<span>☑️</span> Continue Setup';
      } else if (!savedSetup.submitSelector) {
        updateStatus('Setup 2/3 complete. Click to finish', 'idle');
        document.getElementById('startBtn').innerHTML = '<span>▶️</span> Finish Setup';
      } else {
        updateStatus('Click "Start Quiz" to begin', 'idle');
      }
    });
  }
});

// Cleanup on popup close
window.addEventListener('unload', () => {
  stopStatusPolling();
});
