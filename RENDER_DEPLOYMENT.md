# 🚀 Render.com Backend Deployment Guide

## 📁 Dockerfile Location

**File:** `mvp_marketing_app/backend/Dockerfile`

---

## ⚙️ Render Configuration

### **Method 1: Manual Configuration (Dashboard)**

When creating a new Web Service on Render:

#### **Step 1: Basic Settings**
- **Name:** `marketing-mvp-backend`
- **Environment:** `Docker`
- **Region:** Oregon (or closest to you)
- **Branch:** `main`

#### **Step 2: Build Settings** ⚠️ IMPORTANT
- **Root Directory:** `mvp_marketing_app/backend`
- **Dockerfile Path:** `Dockerfile` (relative to root directory)

**OR use full path:**
- **Root Directory:** (leave empty)
- **Dockerfile Path:** `mvp_marketing_app/backend/Dockerfile`

#### **Step 3: Docker Command** (Optional)
If needed, set:
- **Docker Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

### **Method 2: Using render.yaml (Automatic)**

I've created a `render.yaml` file at the repository root.

1. **Push to GitHub:**
   ```bash
   git add render.yaml
   git commit -m "Add Render configuration"
   git push
   ```

2. **In Render Dashboard:**
   - Go to "Blueprint" or "New +"
   - Select "Blueprint"
   - Connect your repository
   - Render will auto-detect `render.yaml`
   - Click "Apply"

3. **Set Secret Environment Variables:**
   - `OPENAI_API_KEY` - Your OpenAI key
   - `QDRANT_API_KEY` - Your Qdrant cloud key

---

## 🔐 Environment Variables

Set these in Render Dashboard → Environment tab:

### **Required:**
```
OPENAI_API_KEY=sk-your-openai-key-here
QDRANT_URL=https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your-qdrant-api-key-here
JWT_SECRET=your-random-secret-key-32-chars-or-more
ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
STORAGE_PATH=/app/storage
```

### **Generate JWT_SECRET:**
```bash
# On Linux/Mac:
openssl rand -base64 32

# On Windows PowerShell:
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))

# Or use any random string generator
```

---

## 📋 Step-by-Step Deployment

### **1. Create Web Service**

1. Go to https://render.com/dashboard
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select your repo: `MVP_Marketing`

### **2. Configure Service**

**Settings:**
```yaml
Name: marketing-mvp-backend
Environment: Docker
Root Directory: mvp_marketing_app/backend
Dockerfile Path: Dockerfile
Branch: main
Region: Oregon (or your region)
Instance Type: Starter ($7/month) or Free (with limitations)
```

### **3. Advanced Settings** (Optional)

**Health Check Path:** `/health`

**Auto-Deploy:** Yes (deploy on push to main)

### **4. Add Environment Variables**

Click **"Environment"** tab and add all required variables listed above.

### **5. Deploy**

Click **"Create Web Service"**

Render will:
1. Clone your repo
2. Build Docker image from `mvp_marketing_app/backend/Dockerfile`
3. Start the container
4. Assign a URL: `https://marketing-mvp-backend.onrender.com`

---

## 🧪 Testing Deployment

### **1. Check Health Endpoint**

Once deployed, test:
```bash
curl https://your-app.onrender.com/health
```

**Expected response:**
```json
{"status": "healthy"}
```

### **2. Check API Root**

```bash
curl https://your-app.onrender.com/
```

**Expected response:**
```json
{
  "message": "Marketing MVP API",
  "version": "1.0.0"
}
```

### **3. Test CORS**

```bash
curl -H "Origin: https://your-frontend.vercel.app" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     https://your-app.onrender.com/api/v1/auth/login
```

Should return CORS headers.

---

## 🐛 Common Issues

### **Issue 1: "No such file or directory" (Your Current Error)**

**Cause:** Render can't find the Dockerfile

**Fix:**
- Set **Root Directory** to `mvp_marketing_app/backend`
- Set **Dockerfile Path** to `Dockerfile`

**OR:**
- Leave Root Directory empty
- Set **Dockerfile Path** to `mvp_marketing_app/backend/Dockerfile`

### **Issue 2: Build Fails - Missing Dependencies**

**Cause:** Python packages missing

**Fix:**
- Check `requirements.txt` is in `mvp_marketing_app/backend/`
- Dockerfile should have: `COPY requirements.txt .`

### **Issue 3: Container Starts But Crashes**

**Cause:** Missing environment variables

**Fix:**
- Check all required env vars are set in Render dashboard
- Check logs: Render Dashboard → Logs tab

### **Issue 4: Port Binding Error**

**Cause:** Not using Render's `$PORT` variable

**Fix:**
- Ensure Dockerfile uses `CMD` with `--port $PORT`
- Or set in Render: Docker Command = `uvicorn main:app --host 0.0.0.0 --port $PORT`

### **Issue 5: Qdrant Connection Fails**

**Cause:** Wrong Qdrant URL or API key

**Fix:**
- Verify `QDRANT_URL` and `QDRANT_API_KEY` in environment variables
- Test connection from backend logs

---

## 📊 Render Plans

### **Free Tier:**
- ✅ 750 hours/month
- ✅ Auto-sleep after 15 min inactivity
- ⚠️ Slower cold starts (~30 seconds)
- ⚠️ Limited resources

**Good for:** Testing, demos

### **Starter ($7/month):**
- ✅ Always on
- ✅ Fast response times
- ✅ More resources
- ✅ No cold starts

**Good for:** Production, small apps

---

## 🔄 Continuous Deployment

Once set up, Render will automatically:
- ✅ Deploy on every push to main branch
- ✅ Build new Docker image
- ✅ Replace old container
- ✅ Zero-downtime deployments

---

## 📝 Post-Deployment Checklist

After successful deployment:

1. **Get Backend URL:**
   - Example: `https://marketing-mvp-backend.onrender.com`

2. **Update Frontend Environment Variable:**
   - In Vercel Dashboard → Settings → Environment Variables
   - Set: `NEXT_PUBLIC_BACKEND_URL = https://marketing-mvp-backend.onrender.com`
   - Redeploy frontend

3. **Update Backend CORS:**
   - In Render Dashboard → Environment
   - Update `ALLOWED_ORIGINS` to include Vercel URL
   - Redeploy backend (or it auto-redeploys)

4. **Test Full Flow:**
   - [ ] Register new user
   - [ ] Login
   - [ ] Upload document
   - [ ] Process request
   - [ ] Check results

---

## 📁 File Structure on Render

Render will see:
```
/ (repository root)
└── mvp_marketing_app/
    └── backend/           ← Root Directory points here
        ├── Dockerfile     ← Render builds from this
        ├── requirements.txt
        ├── main.py
        ├── models.py
        ├── db.py
        ├── api/
        ├── core/
        └── rag/
```

---

## 🔍 Viewing Logs

**Real-time logs:**
1. Render Dashboard
2. Select your service
3. Click "Logs" tab
4. See live output from your application

**Look for:**
```
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

---

## ✅ Summary

**Dockerfile Location:**
```
mvp_marketing_app/backend/Dockerfile
```

**Render Configuration:**
```
Root Directory: mvp_marketing_app/backend
Dockerfile Path: Dockerfile
```

**Or:**
```
Root Directory: (empty)
Dockerfile Path: mvp_marketing_app/backend/Dockerfile
```

**Environment Variables:** Set all in Render dashboard

**Deploy:** Render will automatically build and deploy! 🚀

