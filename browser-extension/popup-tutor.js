// StudyFlow AI Tutor - Popup Logic (Legal Mode)

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
    alert('StudyFlow AI Tutor\n\nHow to use:\n1. Navigate to any quiz page\n2. The sidebar will automatically detect questions\n3. Read the step-by-step explanation\n4. Understand the concept\n5. Click your answer manually\n\nThis is a legal tutoring tool compliant with Missouri HB 2271.\n\nFor support: support@studyflowsuite.com');
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
