# 💾 Database Persistence Fix - Complete

## ❌ **Problem:**

User accounts were being deleted every time you restarted the Docker container. You had to re-register with the same email after each restart.

### **Root Cause:**

The SQLite database file (`marketing_mvp.db`) was stored **inside the Docker container** without a persistent volume, so it was deleted when the container restarted.

---

## ✅ **Solution:**

Added a **Docker volume** to persist the database across container restarts.

---

## 📝 **Changes Made:**

### **1. Added Database Volume to docker-compose.yml**

```yaml
# Before:
volumes:
  - backend_storage:/app/storage

# After:
volumes:
  - backend_storage:/app/storage
  - backend_db:/app/db          ← NEW: Persistent database volume
```

And declared the volume:

```yaml
volumes:
  qdrant_storage:
  backend_storage:
  backend_db:                    ← NEW
```

### **2. Updated Database Path in db.py**

```python
# Before:
DATABASE_URL = "sqlite:///./marketing_mvp.db"
# Stored at: /app/marketing_mvp.db (inside container, not persistent)

# After:
DB_DIR = os.getenv("DB_PATH", "/app/db")
os.makedirs(DB_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR}/marketing_mvp.db"
# Stored at: /app/db/marketing_mvp.db (in Docker volume, persistent!)
```

### **3. Updated Dockerfile**

```dockerfile
# Before:
RUN mkdir -p storage

# After:
RUN mkdir -p storage db
```

---

## 🔄 **What Persists Now:**

### ✅ **Across Container Restarts:**
- **User accounts** (email, password, subscription status)
- **Database records** (users, documents metadata, jobs, templates)
- **Uploaded files** (in `backend_storage` volume)
- **Qdrant data** (in `qdrant_storage` volume)

### ❌ **Still Cleared on Login:**
- **User's Qdrant collection** (document vectors)
- **User's uploaded files** (physical files)
- **User's document records** (metadata in database)

**Why?** This is intentional - we implemented auto-clear on login for fresh sessions.

---

## 🎯 **User Experience Flow:**

### **Before Fix:**

```
Day 1:
├─ Register user@example.com
├─ Upload documents
├─ Process requests
└─ Stop Docker

Day 2:
├─ Start Docker
├─ ❌ User account GONE
└─ ❌ Have to register again
```

### **After Fix:**

```
Day 1:
├─ Register user@example.com
├─ Upload documents
├─ Process requests
└─ Stop Docker

Day 2:
├─ Start Docker
├─ ✅ User account PERSISTS
├─ Login with same email/password
└─ ✅ Works! (documents cleared as designed)
```

---

## 📊 **What's in Each Volume:**

### **1. backend_db** (NEW!)
```
/app/db/
└── marketing_mvp.db      ← SQLite database (PERSISTS!)
    ├── users table       ← User accounts
    ├── documents table   ← Document metadata
    ├── jobs table        ← Processing results
    └── prompt_templates  ← Custom templates
```

### **2. backend_storage**
```
/app/storage/
├── 1/                    ← User 1's files
│   ├── doc1.pdf
│   └── doc2.pptx
└── 2/                    ← User 2's files
```

### **3. qdrant_storage**
```
/qdrant/storage/
└── collections/
    ├── user_1_documents/
    └── user_2_documents/
```

---

## 🧪 **Testing the Fix:**

### **Test 1: Restart Container**

```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'

# Restart Docker
docker-compose restart backend

# Try to login (should work now!)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'
```

**Expected:** ✅ Login succeeds (account persists!)

### **Test 2: Full Docker Down/Up**

```bash
# Register
# (use frontend or curl)

# Stop everything
docker-compose down

# Start again
docker-compose up -d

# Login
# (use frontend or curl)
```

**Expected:** ✅ Login succeeds (database persisted!)

---

## 🔍 **Verify Database Location:**

Check where the database file is now stored:

```bash
# Inside the container:
docker-compose exec backend ls -la /app/db/

# Should show:
# marketing_mvp.db
```

Check the volume:

```bash
docker volume ls

# Should show:
# mvp_marketing_app_backend_db
# mvp_marketing_app_backend_storage
# mvp_marketing_app_qdrant_storage
```

---

## 🗑️ **Auto-Clear Still Active:**

Remember, on login the system still clears:
1. ✅ User's Qdrant collection
2. ✅ User's uploaded files
3. ✅ User's document records

**But keeps:**
1. ✅ User account (email, password)
2. ✅ Other users' data
3. ✅ Job history (if you haven't cleared it)

---

## 🔒 **Data Safety:**

### **To Backup Database:**

```bash
# Copy database from volume to local machine
docker cp marketing-mvp-backend:/app/db/marketing_mvp.db ./backup.db
```

### **To Restore Database:**

```bash
# Copy local database to volume
docker cp ./backup.db marketing-mvp-backend:/app/db/marketing_mvp.db
```

### **To Clear All Data (Reset):**

```bash
# Stop services
docker-compose down

# Remove volumes (deletes ALL data!)
docker volume rm mvp_marketing_app_backend_db
docker volume rm mvp_marketing_app_backend_storage
docker volume rm mvp_marketing_app_qdrant_storage

# Start fresh
docker-compose up -d
```

---

## 📁 **File Changes Summary:**

1. **docker-compose.yml**
   - Added `backend_db:/app/db` volume mount
   - Declared `backend_db` volume

2. **backend/db.py**
   - Changed database path to `/app/db/marketing_mvp.db`
   - Creates directory if it doesn't exist

3. **backend/Dockerfile**
   - Creates `db` directory during build

---

## ✅ **Summary:**

**Fixed:** User accounts now persist across Docker restarts

**How:** 
- Database stored in Docker volume `backend_db`
- Volume persists even when container is deleted
- User accounts remain intact

**Test it:**
1. Register a new user
2. Restart Docker: `docker-compose restart backend`
3. Login with same credentials
4. ✅ Should work without re-registering!

🎉 **Database persistence is now active!** Your user accounts will survive container restarts.

