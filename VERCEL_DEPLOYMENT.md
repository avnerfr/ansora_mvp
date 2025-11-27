# 🚀 Vercel Deployment Guide

## 📋 Project Overview

Your Marketing MVP consists of:
- **Frontend:** Next.js 14 (TypeScript) ✅ Vercel-compatible
- **Backend:** FastAPI (Python) ❌ NOT Vercel-compatible

---

## 🎯 Recommended Deployment Strategy

### **Split Deployment:**
1. **Frontend** → Vercel
2. **Backend** → Railway/Render/Fly.io

---

## 🔧 Step-by-Step Deployment

### **Part 1: Deploy Backend First**

You need to deploy the backend before the frontend so you have a URL.

#### **Option A: Railway (Recommended - Easiest)**

1. **Sign up:** https://railway.app
2. **Create New Project** → Deploy from GitHub
3. **Select** your repo
4. **Settings:**
   - Root Directory: `mvp_marketing_app/backend`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Add environment variables:
     ```
     OPENAI_API_KEY=your-key
     QDRANT_URL=https://your-cloud-qdrant-url
     QDRANT_API_KEY=your-qdrant-key
     JWT_SECRET=your-secret-key
     ALLOWED_ORIGINS=https://your-frontend-url.vercel.app
     STORAGE_PATH=/app/storage
     ```

5. **Deploy** → Get your backend URL (e.g., `https://your-app.railway.app`)

#### **Option B: Render**

1. **Sign up:** https://render.com
2. **New Web Service**
3. **Settings:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Root Directory: `mvp_marketing_app/backend`
   - Add environment variables (same as above)

4. **Deploy** → Get your backend URL

---

### **Part 2: Deploy Frontend to Vercel**

#### **Step 1: Prepare Frontend**

Create `.env.production` file:

```bash
cd mvp_marketing_app/frontend
```

Create `mvp_marketing_app/frontend/.env.production`:
```env
NEXT_PUBLIC_BACKEND_URL=https://your-backend-url.railway.app
```

#### **Step 2: Update CORS in Backend**

Update your backend's `ALLOWED_ORIGINS` to include your Vercel URL:
```env
ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:3000
```

#### **Step 3: Deploy to Vercel**

**Option 1: Via Vercel Dashboard**

1. **Sign up/Login:** https://vercel.com
2. **Import Project** → Connect GitHub
3. **Select** your repository
4. **Configure:**
   - Framework Preset: **Next.js**
   - Root Directory: `mvp_marketing_app/frontend`
   - Build Command: `npm run build` (auto-detected)
   - Output Directory: `.next` (auto-detected)
   - Install Command: `npm install` (auto-detected)

5. **Environment Variables:**
   ```
   NEXT_PUBLIC_BACKEND_URL=https://your-backend-url.railway.app
   ```

6. **Deploy** → Wait for build to complete

**Option 2: Via Vercel CLI**

```bash
# Install Vercel CLI
npm i -g vercel

# Navigate to frontend
cd mvp_marketing_app/frontend

# Login
vercel login

# Deploy
vercel

# Follow prompts:
# - Set up and deploy? Yes
# - Which scope? (your account)
# - Link to existing project? No
# - Project name? marketing-mvp-frontend
# - Directory? ./
# - Auto-detected Next.js. Continue? Yes
# - Override settings? No

# Add environment variable
vercel env add NEXT_PUBLIC_BACKEND_URL production
# Enter: https://your-backend-url.railway.app

# Deploy to production
vercel --prod
```

---

## 📋 Vercel Project Settings

When setting up on Vercel dashboard:

```yaml
Framework Preset: Next.js
Root Directory: mvp_marketing_app/frontend
Build Command: npm run build
Output Directory: .next
Install Command: npm install
Development Command: npm run dev
Node.js Version: 18.x or 20.x
```

**Environment Variables:**
```
NEXT_PUBLIC_BACKEND_URL = https://your-backend-url.railway.app
```

---

## 🔒 Security Checklist

Before deploying:

### **Backend:**
- [ ] Set strong `JWT_SECRET` (use random 32+ char string)
- [ ] Update `ALLOWED_ORIGINS` with production frontend URL
- [ ] Verify `OPENAI_API_KEY` is set
- [ ] Verify `QDRANT_URL` and `QDRANT_API_KEY` are set
- [ ] Check that sensitive data is in environment variables (not code)

### **Frontend:**
- [ ] Update `NEXT_PUBLIC_BACKEND_URL` to production backend
- [ ] Remove any console.logs or debug code
- [ ] Test authentication flow
- [ ] Test document upload
- [ ] Test RAG processing

---

## 🧪 Testing Deployment

### **After Backend Deployment:**

1. **Test health endpoint:**
   ```bash
   curl https://your-backend-url.railway.app/health
   # Should return: {"status":"healthy"}
   ```

2. **Test CORS:**
   ```bash
   curl -H "Origin: https://your-app.vercel.app" \
        -H "Access-Control-Request-Method: POST" \
        -X OPTIONS \
        https://your-backend-url.railway.app/api/v1/auth/login
   ```

### **After Frontend Deployment:**

1. Visit: `https://your-app.vercel.app`
2. Test registration
3. Test login
4. Test document upload
5. Test RAG processing
6. Check browser console for errors

---

## 🐛 Common Issues

### **Issue 1: CORS Errors**

**Error:** "Access to fetch at... has been blocked by CORS policy"

**Fix:**
- Update backend `ALLOWED_ORIGINS` environment variable
- Restart backend service
- Clear browser cache

### **Issue 2: Backend URL Not Found**

**Error:** "Failed to fetch" or "Network error"

**Fix:**
- Check `NEXT_PUBLIC_BACKEND_URL` in Vercel environment variables
- Verify backend is running (visit `/health` endpoint)
- Check backend logs for errors

### **Issue 3: Authentication Fails**

**Error:** 401 Unauthorized

**Fix:**
- Check JWT_SECRET is set on backend
- Clear browser localStorage
- Try logging in again

### **Issue 4: File Upload Fails**

**Error:** "Failed to upload"

**Fix:**
- Check `STORAGE_PATH` is set on backend
- Verify backend has write permissions
- Check file size limits

---

## 💰 Cost Estimate

### **Vercel (Frontend):**
- **Hobby:** Free (perfect for testing)
  - 100GB bandwidth
  - 100 build hours
  - Unlimited projects

- **Pro:** $20/month (if you need more)
  - 1TB bandwidth
  - 400 build hours
  - Team features

### **Railway (Backend):**
- **Free Trial:** $5 credit (limited time)
- **Developer:** $5/month minimum
  - Pay for what you use
  - ~$10-20/month for small app

### **Render (Backend):**
- **Free Tier:** Available (with limitations)
  - Spins down after inactivity
  - Slower cold starts
- **Starter:** $7/month (always on)

### **Cloud Qdrant:**
- You're already using this (external)
- Cost: Check your Qdrant cloud plan

---

## 🔄 Continuous Deployment

Once set up, both Vercel and Railway/Render will:
- ✅ Auto-deploy on git push to main
- ✅ Build previews for pull requests
- ✅ Rollback on failures
- ✅ Show deployment logs

---

## 📚 Additional Resources

- **Vercel Docs:** https://vercel.com/docs
- **Railway Docs:** https://docs.railway.app
- **Render Docs:** https://render.com/docs
- **Next.js Deployment:** https://nextjs.org/docs/deployment

---

## ✅ Quick Checklist

**Before deploying:**
- [ ] Push code to GitHub
- [ ] Create `.env.production` with backend URL
- [ ] Test locally with production build (`npm run build`)
- [ ] Remove sensitive data from code

**Backend deployment:**
- [ ] Choose platform (Railway/Render)
- [ ] Set environment variables
- [ ] Deploy backend
- [ ] Test `/health` endpoint
- [ ] Note backend URL

**Frontend deployment:**
- [ ] Update `NEXT_PUBLIC_BACKEND_URL`
- [ ] Deploy to Vercel
- [ ] Add environment variables in Vercel dashboard
- [ ] Test full application flow

**After deployment:**
- [ ] Update backend CORS with frontend URL
- [ ] Test registration/login
- [ ] Test document upload
- [ ] Test RAG processing
- [ ] Monitor logs for errors

---

## 🎉 Summary

**Vercel Project Type:** **Next.js**  
**Root Directory:** `mvp_marketing_app/frontend`  
**Backend Platform:** Railway or Render (not Vercel)

Your frontend will be lightning-fast on Vercel's edge network, while your backend runs on a platform that supports Python/Docker!

