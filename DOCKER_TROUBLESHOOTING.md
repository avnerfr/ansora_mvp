# Docker Troubleshooting Guide

## ❌ Error: "The system cannot find the file specified" for Docker Desktop

This error means **Docker Desktop is not running** on Windows.

## ✅ Solution 1: Start Docker Desktop

1. **Open Docker Desktop** from your Start menu or desktop shortcut
2. **Wait for it to fully start** - you'll see a green icon in the system tray when ready
3. **Verify it's running:**
   ```powershell
   docker ps
   ```
   Should return a list of containers (or empty if none running)

4. **Then start your services:**
   ```powershell
   cd mvp_marketing_app
   docker-compose up -d
   ```

## ✅ Solution 2: Run Backend Without Docker (Use Cloud Qdrant)

If you don't want to use Docker Desktop, you can run the backend directly and use the **cloud Qdrant instance** instead of local Docker Qdrant.

### Steps:

1. **Install Python dependencies:**
   ```powershell
   cd mvp_marketing_app\backend
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   Create a `.env` file in `mvp_marketing_app\backend\`:
   ```env
   JWT_SECRET=your-secret-key-here-min-32-chars
   OPENAI_API_KEY=your-openai-key
   QDRANT_URL=https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333
   QDRANT_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.s53XfrTWp0MHokNbtLSx2ikhLdi9Miru2Q99NxACFo8
   ALLOWED_ORIGINS=http://localhost:3000
   STORAGE_PATH=./storage
   ```

3. **Run the backend:**
   ```powershell
   cd mvp_marketing_app\backend
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### ⚠️ Note:
When using cloud Qdrant, user document collections will be stored in the cloud instance, not locally. Make sure you're using a different collection name pattern or namespace to avoid conflicts.

## 🔍 Verify Docker Desktop Status

**Check if Docker Desktop is running:**
```powershell
# Should return Docker version info
docker --version

# Should return running containers (or empty list)
docker ps

# If you get "error during connect" - Docker Desktop is NOT running
```

## 🐛 Common Issues

### Issue: Docker Desktop won't start
- **Check Windows WSL 2:** Docker Desktop requires WSL 2 on Windows
- **Restart Docker Desktop:** Close completely and reopen
- **Check system requirements:** Ensure virtualization is enabled in BIOS

### Issue: Port 6333 already in use
- **Stop existing Qdrant:** `docker stop marketing-mvp-qdrant`
- **Or change port** in `docker-compose.yml`:
  ```yaml
  ports:
    - "6335:6333"  # Use different host port
  ```

### Issue: Backend can't connect to Qdrant
- **Check Qdrant is running:** `docker ps` should show `marketing-mvp-qdrant`
- **Check logs:** `docker logs marketing-mvp-qdrant`
- **Verify URL:** Backend should use `http://qdrant:6333` (Docker network name)

