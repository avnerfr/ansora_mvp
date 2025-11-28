# 🐛 Deployment Login Issues - Debug Guide

## 🔍 Common Issues & Fixes

### Issue 1: CORS Error (Most Common)

**Symptoms:**
- Network error in browser console
- "CORS policy" error
- Request blocked

**Fix:**

1. **In Render Dashboard:**
   - Go to your backend service
   - Environment Variables
   - Update `ALLOWED_ORIGINS`:
   ```
   ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
   ```
   - **Important:** Use your EXACT Vercel URL (no trailing slash)
   - Save and wait for redeploy

2. **Find Your Vercel URL:**
   - Vercel Dashboard → Your Project → Domains
   - Copy the URL (e.g., `https://ansora-mvp.vercel.app`)

---

### Issue 2: Backend URL Not Set in Frontend

**Symptoms:**
- Requests going to wrong URL
- 404 errors
- "Failed to fetch"

**Fix:**

1. **In Vercel Dashboard:**
   - Settings → Environment Variables
   - Add/Update:
   ```
   Key: NEXT_PUBLIC_BACKEND_URL
   Value: https://your-backend.onrender.com
   ```
   - **Important:** No trailing slash!
   - Select all environments (Production, Preview, Development)
   - Save

2. **Find Your Render URL:**
   - Render Dashboard → Your backend service
   - Copy the URL at the top (e.g., `https://marketing-mvp-backend.onrender.com`)

3. **Redeploy Frontend:**
   - Vercel → Deployments → Redeploy

---

### Issue 3: Missing Environment Variables on Render

**Symptoms:**
- 500 Internal Server Error
- Backend logs show errors
- "JWT_SECRET not set" or similar

**Required Environment Variables on Render:**

```bash
# REQUIRED
OPENAI_API_KEY=sk-your-openai-key-here
JWT_SECRET=your-random-32-char-secret
QDRANT_URL=https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your-qdrant-api-key

# REQUIRED for CORS
ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000

# REQUIRED for storage
STORAGE_PATH=/app/storage

# Optional (for cloud Qdrant search)
CLOUD_QDRANT_URL=https://your-cloud-qdrant.io:6333
CLOUD_QDRANT_API_KEY=your-cloud-api-key
```

**How to Set:**
1. Render Dashboard → Your service
2. Environment tab
3. Add each variable
4. Save (triggers redeploy)

---

### Issue 4: Database Not Initialized

**Symptoms:**
- "Table doesn't exist" errors
- Registration fails with 500 error
- Backend logs show SQLAlchemy errors

**Fix:**

The database initializes automatically on startup (`init_db()` in `main.py`), but:

1. **Check Render Logs:**
   ```
   Render Dashboard → Your service → Logs
   ```
   - Look for: "Application startup complete"
   - Check for errors during startup

2. **Verify Database Volume:**
   - Render should create `/app/db` automatically
   - Check logs for permission errors

---

### Issue 5: Password Hashing Issues

**Symptoms:**
- "Password cannot be longer than 72 bytes"
- Registration fails with cryptic error

**Fix:**

Already handled in code (using bcrypt directly), but verify:

1. **Password must be < 72 characters**
2. **Frontend should enforce this:**
   - Add maxLength validation in forms

---

## 🧪 Step-by-Step Debugging

### Step 1: Test Backend Health

```bash
curl https://your-backend.onrender.com/health
```

**Expected:** `{"status":"healthy"}`

**If fails:** Backend not running or wrong URL

---

### Step 2: Test CORS

Open browser console on Vercel site, then:

```javascript
fetch('https://your-backend.onrender.com/health')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error)
```

**Expected:** `{status: "healthy"}`

**If CORS error:** Check `ALLOWED_ORIGINS` on Render

---

### Step 3: Test Registration (Backend Directly)

```bash
curl -X POST https://your-backend.onrender.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123",
    "is_subscribed": false
  }'
```

**Expected:**
```json
{
  "access_token": "eyJ..."
}
```

**If fails:** Check backend logs on Render

---

### Step 4: Test Registration (Frontend)

1. Open your Vercel site
2. Open browser DevTools (F12)
3. Go to Network tab
4. Try to register
5. Check the request:
   - URL should be: `https://your-backend.onrender.com/api/v1/auth/register`
   - Status should be: 200
   - Response should have: `access_token`

**Common Issues:**
- Wrong URL → Check `NEXT_PUBLIC_BACKEND_URL` in Vercel
- CORS error → Check `ALLOWED_ORIGINS` in Render
- 500 error → Check Render logs

---

### Step 5: Check Backend Logs

1. **Render Dashboard → Your service → Logs**
2. Look for errors:
   ```
   ERROR: ...
   ```
3. Common errors:
   - `JWT_SECRET not set` → Add environment variable
   - `OPENAI_API_KEY not set` → Add environment variable
   - `Failed to connect to Qdrant` → Check QDRANT_URL and QDRANT_API_KEY
   - `Permission denied` → Check STORAGE_PATH

---

## 🔧 Quick Fixes Checklist

### On Render (Backend):

- [ ] Service is running (not stopped)
- [ ] Environment variables set:
  - [ ] `JWT_SECRET`
  - [ ] `OPENAI_API_KEY`
  - [ ] `QDRANT_URL`
  - [ ] `QDRANT_API_KEY`
  - [ ] `ALLOWED_ORIGINS` (includes Vercel URL)
  - [ ] `STORAGE_PATH`
- [ ] Build completed successfully
- [ ] No errors in logs
- [ ] Health endpoint works: `/health`

### On Vercel (Frontend):

- [ ] Build completed successfully
- [ ] Environment variable set:
  - [ ] `NEXT_PUBLIC_BACKEND_URL` (Render URL)
- [ ] Root Directory set to: `frontend`
- [ ] No build errors
- [ ] Site loads (no 404)

---

## 🔍 Detailed Log Analysis

### What to Look For in Render Logs:

#### ✅ **Good Signs:**
```
INFO:     Uvicorn running on http://0.0.0.0:10000
INFO:     Application startup complete.
INFO:     Started server process
```

#### ❌ **Bad Signs:**
```
ERROR: JWT_SECRET is not set
ERROR: OPENAI_API_KEY is not set
ERROR: Failed to connect to database
ERROR: Permission denied: '/app/db'
```

---

## 🚨 Emergency Reset

If nothing works:

### Reset Render Service:

1. **Render Dashboard → Your service**
2. **Manual Deploy → Clear build cache & deploy**
3. **Or:** Delete service and recreate

### Reset Vercel Deployment:

1. **Vercel Dashboard → Your project**
2. **Deployments → Redeploy**
3. **Check "Clear Cache"**

---

## 📞 Getting More Info

### Backend Request Logging

Add this to see what's happening:

**In Render Environment Variables:**
```
LOG_LEVEL=DEBUG
```

Then check logs for detailed request info.

### Frontend Network Debugging

1. Open DevTools (F12)
2. Network tab
3. Filter: XHR
4. Try to register/login
5. Click the failed request
6. Check:
   - **Headers** → Request URL, Origin
   - **Response** → Error message
   - **Console** → JavaScript errors

---

## 🎯 Most Likely Issue

Based on typical deployment problems:

### 🔥 **90% of login issues are:**

1. **CORS:** `ALLOWED_ORIGINS` doesn't include Vercel URL
2. **Backend URL:** `NEXT_PUBLIC_BACKEND_URL` not set in Vercel
3. **JWT Secret:** `JWT_SECRET` not set in Render

### **Quick Fix:**

```bash
# Render Environment Variables:
ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:3000
JWT_SECRET=your-random-secret-at-least-32-chars
OPENAI_API_KEY=sk-your-key

# Vercel Environment Variables:
NEXT_PUBLIC_BACKEND_URL=https://your-backend.onrender.com
```

**Then redeploy both!**

---

## 🆘 Still Not Working?

### Share these for debugging:

1. **Vercel URL:** `https://_____.vercel.app`
2. **Render URL:** `https://_____.onrender.com`
3. **Backend logs:** Last 50 lines from Render
4. **Browser console error:** Full error message
5. **Network request:** 
   - Request URL
   - Response status
   - Response body

---

## 📋 Working Configuration Example

### Render Environment Variables:
```bash
JWT_SECRET=SuperSecretKeyForJWTTokenGeneration32Chars
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
QDRANT_URL=https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your-api-key-here
CLOUD_QDRANT_URL=https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333
CLOUD_QDRANT_API_KEY=your-api-key-here
ALLOWED_ORIGINS=https://ansora-mvp.vercel.app,http://localhost:3000
STORAGE_PATH=/app/storage
```

### Vercel Environment Variables:
```bash
NEXT_PUBLIC_BACKEND_URL=https://marketing-mvp-backend.onrender.com
```

---

## ✅ Success Indicators

You'll know it's working when:

1. **Backend health check:** ✅
   ```bash
   curl https://your-backend.onrender.com/health
   # Returns: {"status":"healthy"}
   ```

2. **Frontend loads:** ✅ No errors in console

3. **Registration works:** ✅ Returns token, redirects

4. **Login works:** ✅ Returns token, redirects

5. **No CORS errors:** ✅ All requests succeed

🎉 **You're live!**

