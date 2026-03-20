// StudyFlow AI Tutor - Popup Logic (Legal Mode)

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

    // Login button
    document.getElementById('loginBtn').addEventListener('click', () => {
      window.auth.showLogin();
    });
  } else {
    // Show main section
    document.getElementById('loginSection').classList.add('hidden');
    document.getElementById('mainSection').classList.remove('hidden');

    // Display user info
    document.getElementById('userEmail').textContent = user.email;

    // Display tier
    let tier = 'Free';
    if (user.subscription_status === 'active' || user.subscription_status === 'trialing') {
      tier = 'Pro';
    } else if (user.is_beta) {
      tier = 'Beta Tester';
    }
    document.getElementById('userTier').textContent = `${tier} Plan`;

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
  }

  // Help link
  document.getElementById('helpLink').addEventListener('click', (e) => {
    e.preventDefault();
    alert('StudyFlow NoteFlow\n\nHow to use:\n1. Upload your class notes on the website\n2. A floating window appears on any webpage\n3. Type questions about your notes\n4. Get AI-guided hints and relevant sections\n5. Find the answer in your own study materials\n\n100% legal - uses YOUR notes to help YOU learn.\n\nFor support: support@studyflowsuite.com');
  });
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
