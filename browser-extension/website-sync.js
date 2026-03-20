// StudyFlow Website Auto-Sync Script
// Automatically syncs login from website to extension
console.log('🔄 StudyFlow website sync script loaded');

// Check if user is logged in and sync to extension
function syncToExtension() {
  try {
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');

    if (token && user) {
      console.log('✅ Found website login, syncing to extension...');

      // Store in extension storage
      chrome.storage.local.set({
        authToken: token,
        refreshToken: localStorage.getItem('refreshToken'),
        tokenExpiresAt: localStorage.getItem('tokenExpiresAt'),
        user: JSON.parse(user)
      }, () => {
        console.log('✅ Synced website login to extension!');
      });
    } else {
      console.log('⚠️ No website login found');
    }
  } catch (error) {
    console.error('❌ Error syncing to extension:', error);
  }
}

// Sync immediately when script loads
syncToExtension();

// Watch for login changes on the website
setInterval(() => {
  const token = localStorage.getItem('token');

  chrome.storage.local.get(['authToken'], (result) => {
    // If website has token but extension doesn't, sync it
    if (token && !result.authToken) {
      console.log('🔄 Detected new website login, syncing...');
      syncToExtension();
    }
    // If website doesn't have token but extension does, user logged out on website
    else if (!token && result.authToken) {
      console.log('🔄 Detected website logout, clearing extension...');
      chrome.storage.local.remove(['authToken', 'refreshToken', 'tokenExpiresAt', 'user']);
    }
  });
}, 2000); // Check every 2 seconds

// Listen for storage events (login/logout on website)
window.addEventListener('storage', (e) => {
  if (e.key === 'token' || e.key === 'user') {
    console.log('🔄 Website localStorage changed, syncing...');
    setTimeout(syncToExtension, 100);
  }
});

console.log('✅ Website sync script active - monitoring for login changes');
