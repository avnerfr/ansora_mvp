# 🐛 Reddit Fields Showing "Unknown" - Debug Guide

## ✅ **What I Fixed:**

### **Issue 1: "type" field hardcoded**

**File:** `backend/rag/vectorstore.py` (line 140)

```python
# BEFORE (WRONG):
"type": "type",  # ❌ Always returns string "type"

# AFTER (FIXED):
"type": point.payload.get('type'),  # ✅ Gets actual value from Qdrant
```

### **Issue 2: Added detailed logging**

Now logs what fields are available in Qdrant:
```python
logger.info(f"Point {i} payload keys: {list(point.payload.keys())}")
logger.info(f"Extracted metadata - author: {metadata['author']}, subreddit: {metadata['subreddit']}, type: {metadata['type']}")
```

---

## 🔍 **How to Debug:**

### **Step 1: Process a Request**

1. Go to your app
2. Enter keywords (e.g., "cybersecurity")
3. Enter a request
4. Click "Process"

### **Step 2: Check Backend Logs**

```bash
docker-compose logs backend --tail 50
```

**Look for lines like:**
```
Point 1 payload keys: ['text', 'author', 'subreddit', 'timestamp', 'thread_url']
Extracted metadata - author: security_expert, subreddit: cybersecurity, type: None
```

---

## 📊 **What to Look For:**

### **Scenario 1: Fields are in payload**

```
Point 1 payload keys: ['text', 'author', 'subreddit', 'type', 'thread_url', 'timestamp']
Extracted metadata - author: john_doe, subreddit: networking, type: comment
```

**Result:** ✅ Should work! If still showing "Unknown", it's a frontend issue.

### **Scenario 2: Fields are missing**

```
Point 1 payload keys: ['text', 'thread_url', 'timestamp']
Extracted metadata - author: None, subreddit: None, type: None
```

**Result:** ❌ Data not in Qdrant. Need to re-add with correct fields.

---

## 🔧 **Solution if Fields are Missing:**

Your Qdrant data needs to have these fields. Check your data insertion script:

### **File:** `data_scrapper/add_to_qdrant.py`

Should look like:
```python
point = PointStruct(
    id=str(uuid.uuid4()),
    vector=embedding,
    payload={
        "text": post["text"],
        "thread_url": post.get("thread_url", ""),
        "author": post.get("author", ""),        # ← Must be here
        "subreddit": post.get("subreddit", ""),  # ← Must be here
        "type": post.get("type", ""),            # ← Must be here
        "timestamp": post.get("timestamp", ""),
        "scraped_at": post.get("scraped_at", "")
    }
)
```

---

## 📋 **Check Your Reddit JSON Data:**

**File:** `data_scrapper/posts_*.json`

Should have these fields:
```json
{
  "text": "Post content...",
  "thread_url": "https://reddit.com/r/...",
  "author": "username",          ← Check if present
  "subreddit": "cybersecurity",  ← Check if present
  "type": "comment",             ← Check if present
  "timestamp": "2024-01-15T...",
  "scraped_at": "2024-01-15T..."
}
```

---

## 🔄 **If Fields are Missing from JSON:**

### **Option 1: Check Original Scraping**

Your Reddit scraping script should capture these fields:

```python
# In reddit_scraping.ipynb or similar
post_data = {
    "text": comment.body,
    "author": str(comment.author),      # ← Capture author
    "subreddit": str(comment.subreddit), # ← Capture subreddit
    "type": "comment",                   # ← Set type
    "thread_url": f"https://reddit.com{comment.permalink}",
    "timestamp": datetime.fromtimestamp(comment.created_utc).isoformat(),
}
```

### **Option 2: Fix Existing JSON**

If your JSON has the data but different field names, map them:

```python
# In add_to_qdrant.py
payload = {
    "text": post["text"],
    "author": post.get("author") or post.get("username") or "Unknown",
    "subreddit": post.get("subreddit") or post.get("sub") or "Unknown",
    "type": post.get("type") or post.get("post_type") or "post",
    ...
}
```

---

## 🎯 **Quick Test:**

### **Check one Reddit post in Qdrant:**

```python
from qdrant_client import QdrantClient

client = QdrantClient(
    url="YOUR_CLOUD_URL",
    api_key="YOUR_API_KEY"
)

# Get one point
results = client.scroll(
    collection_name="reddit_posts",
    limit=1,
    with_payload=True
)

point = results[0][0] if results[0] else None
if point:
    print("Payload keys:", list(point.payload.keys()))
    print("Author:", point.payload.get('author'))
    print("Subreddit:", point.payload.get('subreddit'))
    print("Type:", point.payload.get('type'))
```

---

## ✅ **Expected vs Actual:**

### **Expected (after fix):**

```
Point 1 payload keys: ['text', 'author', 'subreddit', 'type', 'thread_url', 'timestamp']
Extracted metadata - author: security_expert, subreddit: cybersecurity, type: comment
```

**Frontend shows:**
- Author: security_expert ✅
- Subreddit: r/cybersecurity ✅
- Post Type: comment ✅

### **Current (if data missing):**

```
Point 1 payload keys: ['text', 'thread_url', 'timestamp']
Extracted metadata - author: None, subreddit: None, type: None
```

**Frontend shows:**
- Author: (blank or undefined) ❌
- Subreddit: (blank or undefined) ❌
- Type: (blank or undefined) ❌

---

## 🔨 **Action Items:**

1. **Check logs** after processing a request
2. **See what payload keys are available**
3. **If fields are missing:**
   - Check your JSON source files
   - Update scraping script if needed
   - Re-add data to Qdrant with correct fields
4. **If fields are present but still showing "Unknown":**
   - Check frontend console for data
   - Verify the data is reaching the frontend

---

## 📝 **Summary of Changes:**

| File | Change | Purpose |
|------|--------|---------|
| `backend/rag/vectorstore.py` | Fixed `"type": "type"` → `"type": point.payload.get('type')` | Get actual type value |
| `backend/rag/vectorstore.py` | Added logging for payload keys | Debug what fields are available |
| `backend/rag/vectorstore.py` | Added logging for extracted metadata | Verify values are extracted |

---

## 🎉 **After you check the logs, let me know:**

1. What payload keys do you see?
2. What values are extracted for author, subreddit, type?
3. Are they showing correctly on the frontend now?

This will help determine if:
- ✅ The fix worked (data is in Qdrant)
- ❌ Need to re-add data to Qdrant with correct fields

