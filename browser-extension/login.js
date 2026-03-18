// Login functionality for browser extension

const API_URL = 'https://studyflowsuite.onrender.com/api';

// Check if already logged in
chrome.storage.local.get(['authToken', 'user'], (result) => {
  if (result.authToken && result.user) {
    // Already logged in, redirect to main popup
    window.location.href = 'popup.html';
  }
});

// Handle login form submission
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;

  const loginBtn = document.getElementById('loginBtn');
  const errorMessage = document.getElementById('errorMessage');
  const successMessage = document.getElementById('successMessage');

  // Hide messages
  errorMessage.style.display = 'none';
  successMessage.style.display = 'none';

  // Disable button and show loading
  loginBtn.disabled = true;
  loginBtn.innerHTML = '<span>Signing in...</span>';

  try {
    const response = await fetch(`${API_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (response.ok) {
      // Store token and user data
      await chrome.storage.local.set({
        authToken: data.token,
        user: data.user
      });

      // Show success message
      successMessage.textContent = 'Login successful! Redirecting...';
      successMessage.style.display = 'block';

      // Redirect to main popup after a short delay
      setTimeout(() => {
        window.location.href = 'popup.html';
      }, 1000);
    } else {
      // Show error message
      errorMessage.textContent = data.error || 'Login failed. Please try again.';
      errorMessage.style.display = 'block';

      // Re-enable button
      loginBtn.disabled = false;
      loginBtn.innerHTML = '<span>Sign In</span>';
    }
  } catch (error) {
    console.error('Login error:', error);
    errorMessage.textContent = 'Connection error. Please check your internet connection.';
    errorMessage.style.display = 'block';

    // Re-enable button
    loginBtn.disabled = false;
    loginBtn.innerHTML = '<span>Sign In</span>';
  }
});

// Handle "Sign up" link
document.getElementById('signupLink').addEventListener('click', (e) => {
  e.preventDefault();
  chrome.tabs.create({
    url: 'https://unclephilburt.github.io/studyflowwebsite/signup.html'
  });
});

