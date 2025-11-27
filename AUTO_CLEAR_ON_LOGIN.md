# 🗑️ Auto-Clear on Login - Implementation

## ✅ What Was Implemented

The system now **automatically clears all user data** when they log in or register:

1. **Qdrant Collection** - Deletes `user_{user_id}_documents` collection
2. **Uploaded Files** - Removes all files from `/storage/{user_id}/` directory
3. **Database Records** - Deletes all Document records for the user

---

## 🔄 When Data is Cleared

### **1. On Login**
Every time a user logs in, their data is cleared:
```
User logs in → Clear all data → Return auth token
```

### **2. On Registration**
When a new user registers, any existing data is cleared:
```
New user registers → Clear data (if exists) → Return auth token
```

---

## 📋 What Gets Cleared

### **1. Qdrant Vector Database**
```
Collection: user_1_documents
Status: DELETED ✓
```
- All document vectors
- All document chunks
- All metadata

### **2. File System**
```
Directory: /app/storage/1/
Status: DELETED ✓
```
- All PDF files
- All PowerPoint files
- All images
- Entire user directory removed

### **3. Database Records**
```
Table: documents
User ID: 1
Records: DELETED ✓
```
- All document metadata
- Filenames, file types, sizes
- Upload timestamps

---

## 📝 Code Implementation

### **1. vectorstore.py** - Added Clear Method

```python
def clear_user_collection(self, user_id: int) -> bool:
    """Delete a user's collection from local Qdrant."""
    collection_name = self.get_collection_name(user_id)
    
    if collection_name exists:
        self.client.delete_collection(collection_name)
        logger.info(f"✓ Cleared collection: {collection_name}")
```

### **2. auth.py** - Added Clear Helper Function

```python
def clear_user_data(user_id: int, db: Session):
    """Clear all user data: Qdrant, files, database."""
    
    # 1. Clear Qdrant collection
    vector_store.clear_user_collection(user_id)
    
    # 2. Delete uploaded files
    shutil.rmtree(f"/app/storage/{user_id}")
    
    # 3. Delete database records
    db.query(Document).filter(Document.user_id == user_id).delete()
```

### **3. auth.py** - Login Endpoint

```python
@router.post("/login")
async def login(user_data: UserLogin, db: Session):
    # ... authentication logic ...
    
    # Clear all user data on login
    clear_user_data(user.id, db)
    
    # Return token
    return TokenResponse(access_token=access_token)
```

### **4. auth.py** - Register Endpoint

```python
@router.post("/register")
async def register(user_data: UserCreate, db: Session):
    # ... create user logic ...
    
    # Clear any existing data
    clear_user_data(new_user.id, db)
    
    # Return token
    return TokenResponse(access_token=access_token)
```

---

## 🔍 Log Output Example

When a user logs in, you'll see:

```bash
INFO - POST /api/v1/auth/login - User: user@example.com (ID: 1)
INFO - Clearing all data for user 1 (user@example.com) on login
INFO - Clearing Qdrant collection for user 1
INFO - ✓ Cleared collection: user_1_documents
INFO - ✓ Deleted storage directory for user 1
INFO - ✓ Deleted 5 document records from database for user 1
INFO - ✓ User 1 login successful
```

---

## 🎯 User Experience Flow

### **Typical Session:**

```
1. User Logs In
   ├─ Data cleared automatically
   └─ Clean slate

2. User Uploads Documents
   ├─ Files saved to /storage/1/
   ├─ Records added to database
   └─ Vectors added to Qdrant

3. User Processes Request
   ├─ Uses uploaded documents (3 sources)
   ├─ Uses Reddit posts (2 sources)
   └─ Gets refined content

4. User Logs Out

5. User Logs In Again
   ├─ All previous data CLEARED
   └─ Must re-upload documents
```

---

## ⚠️ Important Notes

### **Data Persistence:**
- ❌ **User documents DO NOT persist** across sessions
- ✅ **Reddit data persists** (in cloud Qdrant)
- ✅ **User account persists** (email, password)
- ❌ **Previous job results ARE NOT stored** (optional feature)

### **What This Means:**
- User must re-upload documents each session
- Fresh start every login
- No accumulation of old/stale documents
- Privacy-focused: no long-term storage

---

## 🧪 Testing

### **Test Scenario 1: Upload → Logout → Login**

1. **Login** as user1
2. **Upload** a PDF file
3. **Check** Qdrant: `user_1_documents` exists ✓
4. **Check** filesystem: `/storage/1/file.pdf` exists ✓
5. **Logout**
6. **Login** again
7. **Check** Qdrant: `user_1_documents` DELETED ✓
8. **Check** filesystem: `/storage/1/` DELETED ✓
9. **Check** database: No documents for user 1 ✓

### **Test Scenario 2: Register New User**

1. **Register** new user (user2)
2. **Check** logs for clear operations
3. **Upload** document
4. **Process** request (should use uploaded doc)
5. **Logout**
6. **Login** again
7. **Process** request (no user docs, only Reddit)

---

## 📊 Database State

### **Before Login:**
```sql
SELECT * FROM documents WHERE user_id = 1;
-- Result: 5 documents

SELECT * FROM users WHERE id = 1;
-- Result: user@example.com (active)
```

### **After Login:**
```sql
SELECT * FROM documents WHERE user_id = 1;
-- Result: 0 documents (CLEARED)

SELECT * FROM users WHERE id = 1;
-- Result: user@example.com (still active)
```

---

## 🚨 Error Handling

The clear operation is **non-blocking**:

```python
try:
    clear_user_data(user.id, db)
except Exception as e:
    logger.error(f"Failed to clear data: {e}")
    # Login continues anyway
```

**Why?**
- Login should not fail due to clearing errors
- User experience is prioritized
- Errors are logged for debugging

---

## 🔧 Configuration

### **To Disable Auto-Clear:**

Comment out the clear calls in `auth.py`:

```python
# Don't clear on login
# clear_user_data(user.id, db)
```

### **To Clear Only Specific Items:**

Modify `clear_user_data()` function:

```python
def clear_user_data(user_id: int, db: Session):
    # Clear only Qdrant (keep files and DB records)
    vector_store.clear_user_collection(user_id)
    
    # Comment out file/DB clearing:
    # shutil.rmtree(...)
    # db.query(Document).delete()
```

---

## 💡 Alternative Approaches

If you want data to persist across sessions:

### **Option 1: Clear Only on Explicit Action**
- Add a "Clear My Data" button in UI
- User manually triggers the clear

### **Option 2: Expire Old Data**
- Clear data older than X days
- Keep recent uploads

### **Option 3: Data Limit**
- Keep only last N uploads
- Delete oldest when limit reached

---

## 🎯 Summary

✅ **Automatic Clearing Active**
- Every login clears all user data
- Includes Qdrant, files, database records
- Non-blocking (errors don't prevent login)
- Logged for transparency

✅ **User Experience:**
- Fresh start each session
- Must re-upload documents
- Still gets Reddit context
- Privacy-focused

✅ **Backend is Running:**
- Ready to test
- Watch logs to see clearing in action
- Files modified: `vectorstore.py`, `auth.py`

🚀 **Test it now by logging in!**

