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

// Function to get auth token
async function getAuthToken() {
  const result = await chrome.storage.local.get(['authToken']);
  return result.authToken || null;
}

// Function to logout
async function logout() {
  await chrome.storage.local.remove(['authToken', 'user', 'rememberMe']);
  window.location.href = 'login.html';
}

// Export functions for use in other scripts
window.auth = {
  getCurrentUser,
  getAuthToken,
  logout
};
