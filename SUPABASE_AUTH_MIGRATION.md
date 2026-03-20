# Supabase Auth Migration - Complete Guide

## ✅ COMPLETED

### 1. Backend Authentication System
**Files Created/Modified:**
- `StudyFlow/backend/supabase_auth.py` - New auth module with Supabase Auth integration
- `StudyFlow/backend/app.py` - Updated all endpoints to use `@supabase_auth_required`

**New Endpoints:**
- `POST /api/signup` - Register with Supabase Auth + create user profile
  - Now accepts `collective_brain_opt_in` parameter
  - Returns `access_token` and `refresh_token`

- `POST /api/login` - Sign in with Supabase Auth
  - Returns `access_token`, `refresh_token`, and `expires_in`
  - Includes user profile data (subscription_tier, etc.)

- `POST /api/refresh` - Refresh expired access token
  - Body: `{"refresh_token": "..."}`
  - Returns new `access_token` and `refresh_token`

- `POST /api/logout` - Invalidate session
  - Requires `Authorization: Bearer <token>` header

- `POST /api/reset-password` - Send password reset email
  - Body: `{"email": "..."}`

**Security Improvements:**
- ✅ JWT validation now handled by Supabase (more secure)
- ✅ Automatic token expiration and refresh
- ✅ Password reset via email (handled by Supabase)
- ✅ Email verification (optional, configurable in Supabase)
- ✅ No more bcrypt/custom JWT dependencies

### 2. Browser Extension
**Files Updated:**
- `browser-extension/login.js` - Now stores `access_token`, `refresh_token`, and `tokenExpiresAt`
- `browser-extension/auth.js` - Automatic token refresh when expired
  - Refreshes token 5 minutes before expiration
  - Fallback to login if refresh fails

**How It Works:**
1. User logs in → receives `access_token` (valid for ~1 hour)
2. Extension stores both access and refresh tokens
3. Before each API call, `getAuthToken()` checks if token is expired
4. If expired, automatically refreshes using `refresh_token`
5. If refresh fails, redirects to login

### 3. Migration Script
**File:** `migrate_users_to_supabase.py`

**What It Does:**
- Connects to old Render PostgreSQL database
- Gets all existing users
- Creates Supabase Auth accounts for each user
- Creates user profiles in Supabase
- Sends password reset emails to all migrated users

**Why Password Resets?**
- Old system used bcrypt hashes (can't recover plain-text passwords)
- Supabase needs plain-text password to create accounts
- Solution: Create accounts with temp passwords → send reset emails

---

## 🚀 DEPLOYMENT STEPS

### Step 1: Update Browser Extension (DO THIS FIRST)

**Why first?** The backend is backward compatible, but the extension needs new token handling.

1. **Package Extension:**
   ```bash
   cd C:\Users\CodyW\OneDrive\Documents\StudyFlow\StudyFlowSuite
   cmd /c update-extension.bat
   ```

2. **Test Extension Locally:**
   - Go to `chrome://extensions`
   - Click "Load unpacked"
   - Select `StudyFlow-Extension` folder
   - Test login with a test account

3. **Verify Token Refresh:**
   - Open DevTools Console in extension popup
   - Look for "🔄 Access token expired, refreshing..." message after ~55 minutes

### Step 2: Deploy Backend to Render

**Environment Variables (already set):**
- ✅ `SUPABASE_URL`
- ✅ `SUPABASE_ANON_KEY`
- ✅ `SUPABASE_SERVICE_KEY`
- ✅ All existing keys (OPENAI, GEMINI, STRIPE, etc.)

**Deploy:**
```bash
cd C:\Users\CodyW\OneDrive\Documents\StudyFlow\StudyFlowSuite
git add .
git commit -m "Migrate to Supabase Auth with automatic token refresh

Backend changes:
- Replace custom JWT with Supabase Auth
- New endpoints: /api/refresh, /api/logout, /api/reset-password
- All endpoints now use @supabase_auth_required decorator
- User profiles now in Supabase with collective_brain_opt_in

Browser extension changes:
- Store access_token and refresh_token separately
- Automatic token refresh 5 minutes before expiration
- Proper logout flow (invalidates session on backend)

Migration script included for existing users

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

git push origin main
```

**Deployment time:** ~2-3 minutes (no new major dependencies)

### Step 3: Migrate Existing Users

**⚠️ CRITICAL: Do this AFTER backend is deployed!**

1. **Set Environment Variables Locally:**
   ```bash
   # In PowerShell:
   $env:SUPABASE_URL="https://xxxxx.supabase.co"
   $env:SUPABASE_SERVICE_KEY="your_service_key"
   $env:DATABASE_URL="your_old_render_postgres_url"
   ```

2. **Run Migration:**
   ```bash
   cd C:\Users\CodyW\OneDrive\Documents\StudyFlow\StudyFlowSuite
   python migrate_users_to_supabase.py
   ```

3. **What Happens:**
   - Creates Supabase Auth accounts for all existing users
   - Sends password reset emails to everyone
   - Maps subscription tiers: `free` → `free`, `premium/pro/beta` → `pro`

4. **Notify Users:**
   Send an email/announcement:
   ```
   Subject: Important: Reset Your StudyFlow Password

   We've upgraded our authentication system for better security.

   Action Required: Check your email for a password reset link.

   What's New:
   - More secure login system
   - Automatic session management
   - No more expired sessions mid-quiz!

   Questions? Reply to this email.
   ```

### Step 4: Test Everything

**Test New User Registration:**
```bash
curl -X POST https://studyflowsuite.onrender.com/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123!","name":"Test User","collective_brain_opt_in":true}'
```

**Expected Response:**
```json
{
  "success": true,
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": {
    "id": "uuid",
    "email": "test@example.com",
    "collective_brain_opt_in": true
  }
}
```

**Test Login:**
```bash
curl -X POST https://studyflowsuite.onrender.com/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123!"}'
```

**Test Protected Endpoint:**
```bash
curl -X GET https://studyflowsuite.onrender.com/api/notes/list \
  -H "Authorization: Bearer <access_token_from_login>"
```

**Test Token Refresh:**
```bash
curl -X POST https://studyflowsuite.onrender.com/api/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token_from_login>"}'
```

---

## 🔄 What Changed for Users?

### Before (Old System):
- Login → get JWT token (valid for 30 days)
- Token stored in extension/frontend
- Manual password hashing with bcrypt

### After (Supabase Auth):
- Login → get `access_token` (1 hour) + `refresh_token` (30 days)
- Extension automatically refreshes token before expiration
- Supabase handles password security, email verification, resets
- Users can reset password via email (no manual intervention)

### Benefits:
1. **Security:** Industry-standard auth (Supabase handles vulnerabilities)
2. **UX:** Seamless token refresh (no more mid-quiz logouts)
3. **Maintenance:** No more manual password reset requests
4. **Features:** Built-in email verification, OAuth (Google/GitHub) support

---

## 📋 Optional: Add OAuth Login (Google, GitHub)

Supabase makes this trivial:

**Step 1:** Go to Supabase Dashboard → Authentication → Providers
**Step 2:** Enable Google/GitHub OAuth
**Step 3:** Update `login.html` to add OAuth buttons:

```html
<button id="googleLoginBtn">
  Sign in with Google
</button>
```

```javascript
// In login.js
document.getElementById('googleLoginBtn').addEventListener('click', async () => {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google'
  });
  // Handle redirect...
});
```

**Benefit:** Users can sign in with one click (no password needed)

---

## 🆘 Troubleshooting

### "Invalid or expired token" errors:
- Check that `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are correct in Render
- Verify user exists in Supabase Auth (Dashboard → Authentication → Users)
- Check token expiration: `jwt.io` → paste token → see `exp` field

### Migration script fails:
- Make sure Supabase allows admin API calls (should be enabled by default)
- Check that `DATABASE_URL` (old Render PostgreSQL) is accessible
- If user already exists: Script will skip them (safe to re-run)

### Token refresh not working in extension:
- Check console for "🔄 Access token expired, refreshing..." message
- Verify `/api/refresh` endpoint is working (test with curl)
- Make sure `refresh_token` is stored in `chrome.storage.local`

---

## 🎉 You're Done!

With Supabase Auth, you now have:
- ✅ Secure, industry-standard authentication
- ✅ Automatic token refresh (better UX)
- ✅ Password reset via email
- ✅ Ready for OAuth (Google, GitHub)
- ✅ Collective Brain opt-in during signup
- ✅ Proper session management

**Next Steps:**
1. Push to GitHub (backend + extension)
2. Migrate existing users
3. Test with real users
4. Monitor Supabase Dashboard for auth issues

Need help? The Supabase dashboard shows all auth events, errors, and user sessions in real-time.
