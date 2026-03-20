// Authentication check for extension pages
// Include this before other scripts on pages that require authentication

(async function checkAuth() {
  const result = await chrome.storage.local.get(['authToken', 'user']);

  // If no auth token, redirect to login page
  if (!result.authToken || !result.user) {
    // Only redirect if we're not already on the login page
    if (!window.location.href.includes('login.html')) {
      window.location.href = 'login.html';
    }
  }
})();

// Function to get current user
async function getCurrentUser() {
  const result = await chrome.storage.local.get(['user']);
  return result.user || null;
}

// Function to get auth token (with automatic refresh if expired)
async function getAuthToken() {
  const result = await chrome.storage.local.get(['authToken', 'refreshToken', 'tokenExpiresAt']);

  // Check if token exists
  if (!result.authToken) {
    return null;
  }

  // Check if token is expired (refresh 5 minutes before actual expiration)
  const now = Date.now();
  const expiresAt = result.tokenExpiresAt || 0;
  const bufferTime = 5 * 60 * 1000; // 5 minutes in milliseconds

  if (now + bufferTime >= expiresAt && result.refreshToken) {
    // Token is expired or will expire soon, refresh it
    console.log('🔄 Access token expired, refreshing...');

    try {
      const response = await fetch('https://studyflowsuite.onrender.com/api/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: result.refreshToken })
      });

      if (response.ok) {
        const data = await response.json();

        // Store new tokens
        await chrome.storage.local.set({
          authToken: data.access_token,
          refreshToken: data.refresh_token,
          tokenExpiresAt: Date.now() + (data.expires_in * 1000)
        });

        console.log('✅ Token refreshed successfully');
        return data.access_token;
      } else {
        // Refresh failed, user needs to log in again
        console.error('❌ Token refresh failed, logging out');
        await logout();
        return null;
      }
    } catch (error) {
      console.error('❌ Token refresh error:', error);
      // On error, try to use existing token
      return result.authToken;
    }
  }

  return result.authToken;
}

// Function to logout
async function logout() {
  // Get current token
  const result = await chrome.storage.local.get(['authToken']);

  // Call backend logout endpoint to invalidate session
  if (result.authToken) {
    try {
      await fetch('https://studyflowsuite.onrender.com/api/logout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${result.authToken}`
        }
      });
    } catch (error) {
      console.error('Logout API error:', error);
      // Continue with local logout even if API call fails
    }
  }

  // Clear local storage
  await chrome.storage.local.remove(['authToken', 'refreshToken', 'tokenExpiresAt', 'user']);

  // Redirect to login
  window.location.href = 'login.html';
}

// Export functions for use in other scripts
window.auth = {
  getCurrentUser,
  getAuthToken,
  logout
};
