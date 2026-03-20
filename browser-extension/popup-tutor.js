// StudyFlow AI Tutor - Popup Logic (Legal Mode)

// Auth helper functions (simplified for popup)
window.auth = {
  async getCurrentUser() {
    const result = await chrome.storage.local.get(['user']);
    return result.user || null;
  },

  async getAuthToken() {
    const result = await chrome.storage.local.get(['authToken']);
    return result.authToken || null;
  },

  showLogin() {
    chrome.tabs.create({
      url: chrome.runtime.getURL('login.html')
    });
  },

  async logout() {
    const result = await chrome.storage.local.get(['authToken']);

    if (result.authToken) {
      try {
        await fetch('https://studyflowsuite.onrender.com/api/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${result.authToken}` }
        });
      } catch (error) {
        console.error('Logout API error:', error);
      }
    }

    await chrome.storage.local.remove(['authToken', 'refreshToken', 'tokenExpiresAt', 'user']);
    window.location.reload();
  }
};

// Helper function to update overlay button state
function updateOverlayButton(state) {
  const btn = document.getElementById('toggleOverlayBtn');
  if (!btn) return;

  if (state === 'opened') {
    btn.textContent = 'Close NoteFlow';
    btn.style.background = 'linear-gradient(135deg, #f87171 0%, #dc2626 100%)';
  } else {
    btn.textContent = 'Open NoteFlow';
    btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  }
}

// Check if overlay is currently open
async function checkOverlayState() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  chrome.tabs.sendMessage(tab.id, { action: 'checkNoteFlowState' }, (response) => {
    if (chrome.runtime.lastError || !response) {
      // Content script not loaded or overlay doesn't exist
      updateOverlayButton('closed');
      return;
    }

    updateOverlayButton(response.isOpen ? 'opened' : 'closed');
  });
}

async function init() {
  const user = await window.auth.getCurrentUser();

  if (!user) {
    // Show login section
    document.getElementById('loginSection').classList.remove('hidden');
    document.getElementById('mainSection').classList.add('hidden');

    // Login form submission
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();

      const email = document.getElementById('emailInput').value;
      const password = document.getElementById('passwordInput').value;
      const errorDiv = document.getElementById('loginError');

      errorDiv.classList.add('hidden');

      try {
        const response = await fetch('https://studyflowsuite.onrender.com/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
          // Store auth data
          await chrome.storage.local.set({
            authToken: data.access_token,
            refreshToken: data.refresh_token,
            tokenExpiresAt: Date.now() + (data.expires_in * 1000),
            user: data.user
          });

          // Reload popup to show main section
          window.location.reload();
        } else {
          errorDiv.textContent = data.error || 'Login failed';
          errorDiv.classList.remove('hidden');
        }
      } catch (error) {
        console.error('Login error:', error);
        errorDiv.textContent = 'Connection error. Please try again.';
        errorDiv.classList.remove('hidden');
      }
    });

    // Signup link
    document.getElementById('signupLink').addEventListener('click', (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: 'https://unclephilburt.github.io/studyflowwebsite/signup.html' });
    });
  } else {
    // Show main section
    document.getElementById('loginSection').classList.add('hidden');
    document.getElementById('mainSection').classList.remove('hidden');

    // Display user info
    const userName = user.name || user.email.split('@')[0];
    document.getElementById('userName').textContent = userName;

    // Set avatar initial
    document.getElementById('userAvatar').textContent = userName.charAt(0).toUpperCase();

    // Display tier
    let tier = 'Free';
    if (user.subscription_status === 'active' || user.subscription_status === 'trialing') {
      tier = 'Pro';
    } else if (user.is_beta) {
      tier = 'Beta Tester';
    }
    document.getElementById('userTier').textContent = `${tier} Plan`;

    // Load stats
    loadStats();

    // Load settings
    loadSettings();

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const tabName = tab.getAttribute('data-tab');
        switchTab(tabName);
      });
    });

    // Check overlay state on load
    checkOverlayState();

    // Toggle NoteFlow Overlay button
    document.getElementById('toggleOverlayBtn').addEventListener('click', async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      // Check if we're on a chrome:// page or extension page
      if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
        alert('⚠️ NoteFlow cannot run on Chrome system pages.\n\nPlease navigate to a regular webpage (like google.com) to use NoteFlow.');
        return;
      }

      chrome.tabs.sendMessage(tab.id, { action: 'toggleNoteFlow' }, (response) => {
        if (chrome.runtime.lastError) {
          console.error('Error toggling overlay:', chrome.runtime.lastError);

          // Try to reload the content script
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ['noteflow-overlay.js']
          }).then(() => {
            // Retry after injecting
            setTimeout(() => {
              chrome.tabs.sendMessage(tab.id, { action: 'toggleNoteFlow' }, (response) => {
                if (response && response.success) {
                  updateOverlayButton(response.state);
                } else {
                  alert('⚠️ Please refresh the page (F5) and try again.');
                }
              });
            }, 100);
          }).catch((error) => {
            console.error('Failed to inject script:', error);
            alert('⚠️ Please refresh the page (F5) to use NoteFlow');
          });
          return;
        }

        if (response && response.success) {
          updateOverlayButton(response.state);
        }
      });
    });

    // Upload Notes button
    document.getElementById('uploadNotesBtn').addEventListener('click', () => {
      chrome.tabs.create({ url: 'https://unclephilburt.github.io/studyflowwebsite/upload.html' });
    });

    // Upgrade button
    document.getElementById('upgradeBtn').addEventListener('click', () => {
      chrome.tabs.create({ url: 'https://unclephilburt.github.io/studyflowwebsite/#pricing' });
    });

    // Hide upgrade button for Pro/Beta users
    if (tier === 'Pro' || tier === 'Beta Tester') {
      document.getElementById('upgradeBtn').style.display = 'none';
    }

    // Logout button
    document.getElementById('logoutBtn').addEventListener('click', () => {
      if (confirm('Are you sure you want to sign out?')) {
        window.auth.logout();
      }
    });

    // Settings change handlers
    document.getElementById('settingCollectiveBrain').addEventListener('change', async (e) => {
      const isEnabled = e.target.checked;
      await chrome.storage.local.set({ settingCollectiveBrain: isEnabled });

      // Update backend
      const token = await window.auth.getAuthToken();
      if (token) {
        try {
          await fetch('https://studyflowsuite.onrender.com/api/settings/collective-brain', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ enabled: isEnabled })
          });
        } catch (error) {
          console.error('Error updating collective brain setting:', error);
        }
      }
    });
  }

  // Help link
  document.getElementById('helpLink').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'https://unclephilburt.github.io/studyflowwebsite/' });
  });
}

// Tab switching function
function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.tab').forEach(tab => {
    if (tab.getAttribute('data-tab') === tabName) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  // Update tab content
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.remove('active');
  });
  document.getElementById(`${tabName}Tab`).classList.add('active');
}

// Load stats from backend
async function loadStats() {
  const token = await window.auth.getAuthToken();
  if (!token) return;

  try {
    const response = await fetch('https://studyflowsuite.onrender.com/api/stats', {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (response.ok) {
      const stats = await response.json();
      document.getElementById('statNotesUploaded').textContent = stats.notes_uploaded || 0;
      document.getElementById('statQuestionsAsked').textContent = stats.questions_asked || 0;
      document.getElementById('statHintsReceived').textContent = stats.hints_received || 0;
      document.getElementById('statStudySessions').textContent = stats.study_sessions || 0;
    }
  } catch (error) {
    console.error('Error loading stats:', error);
  }
}

// Load settings from storage
async function loadSettings() {
  const token = await window.auth.getAuthToken();
  if (!token) return;

  try {
    // Load from backend
    const response = await fetch('https://studyflowsuite.onrender.com/api/settings/collective-brain', {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (response.ok) {
      const data = await response.json();
      document.getElementById('settingCollectiveBrain').checked = data.enabled !== false;
      await chrome.storage.local.set({ settingCollectiveBrain: data.enabled !== false });
    } else {
      // Fallback to local storage
      const result = await chrome.storage.local.get(['settingCollectiveBrain']);
      document.getElementById('settingCollectiveBrain').checked = result.settingCollectiveBrain !== false;
    }
  } catch (error) {
    console.error('Error loading settings:', error);
    // Fallback to local storage
    const result = await chrome.storage.local.get(['settingCollectiveBrain']);
    document.getElementById('settingCollectiveBrain').checked = result.settingCollectiveBrain !== false;
  }
}

// Initialize when popup opens
init();

// Listen for auth state changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.jwtToken) {
    // Re-initialize when login state changes
    init();
  }
});
