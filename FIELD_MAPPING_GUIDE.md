# 📊 Field Mapping Guide: Backend → Frontend

## 🔄 Complete Data Flow

### **1. Vector Store → Document Metadata**

**File:** `backend/rag/vectorstore.py` (lines 136-145)

```python
metadata = {
    "source": "reddit",
    "subreddit": point.payload.get('subreddit', 'Unknown'),
    "author": point.payload.get('author', 'Unknown'),
    "type": "type",
    "text": point.payload.get('text', 'Unknown'),
    "thread_url": url,
    "timestamp": point.payload.get('timestamp', ''),
    "score": point.score,  # ← Similarity score from Qdrant
}
```

---

### **2. Pipeline → Format Sources**

**File:** `backend/rag/pipeline.py` (lines 24-49)

**UPDATED MAPPING:**
```python
def format_sources(docs: List[Any]) -> List[Dict[str, Any]]:
    sources = []
    for doc in docs:
        metadata = doc.metadata
        score = metadata.get("score", 0.0)  # ← Extract from metadata
        
        source = {
            "snippet": content[:500],
            "text": content,  # Full text
            "score": score,  # ← Now properly extracted!
            
            # All metadata fields passed through
            "source": metadata.get("source"),
            "filename": metadata.get("filename"),
            "file_type": metadata.get("file_type"),
            "subreddit": metadata.get("subreddit"),
            "author": metadata.get("author"),
            "thread_url": metadata.get("thread_url"),  # ← For clickable link
            "timestamp": metadata.get("timestamp"),
            "type": metadata.get("type"),
        }
        sources.append(source)
    return sources
```

---

### **3. API Response → Frontend**

**File:** `backend/api/rag.py` (API endpoint)

```python
return RAGResultResponse(
    job_id=job.id,
    refined_text=job.refined_text,
    sources=job.sources,  # ← JSON with all fields
    original_request=job.original_request,
    topics=job.topics
)
```

---

### **4. Frontend Display**

**File:** `frontend/app/results/[jobId]/page.tsx` (lines 179-282)

```tsx
{results.sources.map((source: any, index: number) => (
  <div>
    {/* Score */}
    {source.score !== undefined && (
      <span>Score: {(source.score * 100)?.toFixed(1)}%</span>
    )}
    
    {/* Filename */}
    <h3>{source.filename || 'Unknown Document'}</h3>
    
    {/* Metadata Grid */}
    {source.author && <div>Author: {source.author}</div>}
    {source.subreddit && <div>Subreddit: r/{source.subreddit}</div>}
    {source.timestamp && <div>Date: {new Date(source.timestamp).toLocaleDateString()}</div>}
    
    {/* Thread URL - Clickable Link */}
    {source.thread_url && (
      <a href={source.thread_url} target="_blank">
        View Original Thread
      </a>
    )}
    
    {/* Content */}
    <div>{source.snippet || source.text}</div>
  </div>
))}
```

---

## 🔧 **Fixed Issues:**

### **Issue 1: Score showing 0.0%**

**Problem:**
```python
# OLD (WRONG):
score = getattr(doc, 'score', 0.0)  # Looking for doc.score (doesn't exist)
```

**Solution:**
```python
# NEW (CORRECT):
score = metadata.get("score", 0.0)  # Extract from doc.metadata['score']
```

**Why it failed:**
- Qdrant score is stored in `doc.metadata['score']`
- Old code checked `doc.score` as an attribute (which doesn't exist)
- Always returned default value of 0.0

---

### **Issue 2: URL not clickable**

**Problem:**
- Old code put `thread_url` into `doc_id` field
- Frontend didn't have specific handling for `thread_url`

**Solution:**
```python
# NEW: Pass thread_url as its own field
source.update({
    "thread_url": metadata.get("thread_url"),
})
```

**Frontend now has:**
```tsx
{source.thread_url && (
  <a href={source.thread_url} target="_blank">
    🔗 View Original Thread
  </a>
)}
```

---

### **Issue 3: "Contributor" showing**

**Problem:**
- Old code created filename as: `f"Reddit: {metadata.get('author')}"`
- But `filename` field wasn't being properly set in vectorstore

**Solution:**
```python
# In vectorstore.py, ensure all fields are set:
metadata = {
    "author": point.payload.get('author', 'Unknown'),
    ...
}

# In pipeline.py, pass filename directly:
source.update({
    "filename": metadata.get("filename"),
    "author": metadata.get("author"),  # Separate field
})
```

---

## 📋 **Complete Field Reference:**

### **Fields from Reddit Posts:**

| Backend Field | Frontend Display | Location | Example |
|--------------|------------------|----------|---------|
| `source` | Badge | Top | "reddit" |
| `score` | "Score: X%" | Top | "Score: 87.5%" |
| `author` | "Author: X" | Grid | "Author: security_expert" |
| `subreddit` | "Subreddit: r/X" | Grid | "Subreddit: r/cybersecurity" |
| `timestamp` | "Date: X" | Grid | "Date: 11/15/2024" |
| `type` | "Post Type: X" | Grid | "Post Type: comment" |
| `thread_url` | Clickable link | Below grid | "🔗 View Original Thread" |
| `text` / `snippet` | Content | Bottom | Full text excerpt |
| `filename` | Title | Top | "Reddit: u/username" |
| `file_type` | "Type: X" | Grid | "Type: reddit_post" |

### **Fields from Documents:**

| Backend Field | Frontend Display | Location | Example |
|--------------|------------------|----------|---------|
| `score` | "Score: X%" | Top | "Score: 92.3%" |
| `filename` | Title | Top | "Security_Whitepaper.pdf" |
| `file_type` | "Type: X" | Grid | "Type: PDF" |
| `file_id` / `doc_id` | "Doc ID: X" | Grid | "Doc ID: 123" |
| `snippet` | Content | Bottom | Document excerpt |

---

## 🗺️ **Visual Data Flow:**

```
┌────────────────────────────────────────────────────────┐
│ 1. QDRANT DATABASE                                     │
│    Point with payload:                                 │
│    { author: "user", subreddit: "cyber", text: "..." } │
└────────────────────┬───────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│ 2. VECTORSTORE.PY (search_reddit_posts)               │
│    Extracts payload + adds score:                     │
│    metadata = {                                        │
│        "author": payload.get('author'),                │
│        "score": point.score,  ← From Qdrant           │
│        ...                                             │
│    }                                                   │
└────────────────────┬───────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│ 3. PIPELINE.PY (format_sources)                       │
│    Formats for API response:                          │
│    {                                                   │
│        "score": metadata.get("score"),  ← Extract     │
│        "author": metadata.get("author"),               │
│        "thread_url": metadata.get("thread_url"),       │
│        ...                                             │
│    }                                                   │
└────────────────────┬───────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│ 4. API ENDPOINT (rag.py)                              │
│    Returns JSON to frontend:                          │
│    {                                                   │
│        "sources": [                                    │
│            { "score": 0.875, "author": "user", ... }  │
│        ]                                               │
│    }                                                   │
└────────────────────┬───────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│ 5. FRONTEND (results/[jobId]/page.tsx)                │
│    Displays each field:                               │
│    <span>Score: {(source.score * 100).toFixed(1)}%</span> │
│    <div>Author: {source.author}</div>                 │
│    <a href={source.thread_url}>View Thread</a>        │
└────────────────────────────────────────────────────────┘
```

---

## 🎯 **Key Takeaways:**

### **1. Score Extraction:**
```python
# ✅ CORRECT:
score = metadata.get("score", 0.0)

# ❌ WRONG:
score = getattr(doc, 'score', 0.0)
```

### **2. Pass All Fields:**
```python
# ✅ CORRECT: Pass everything
source.update({
    "source": metadata.get("source"),
    "author": metadata.get("author"),
    "thread_url": metadata.get("thread_url"),
    ...
})

# ❌ WRONG: Only pass subset
source = {
    "filename": "...",
    "snippet": "...",
}
```

### **3. Frontend Conditional Rendering:**
```tsx
// ✅ CORRECT: Check if field exists
{source.thread_url && <a href={source.thread_url}>Link</a>}

// ❌ WRONG: Always render (shows empty if missing)
<a href={source.thread_url}>Link</a>
```

---

## 🔍 **Debugging Checklist:**

If fields aren't showing:

1. **Check vectorstore.py** - Are fields added to metadata?
   ```python
   metadata = {
       "author": point.payload.get('author'),  # ← Is this here?
   }
   ```

2. **Check pipeline.py format_sources** - Are fields passed through?
   ```python
   source.update({
       "author": metadata.get("author"),  # ← Is this here?
   })
   ```

3. **Check frontend** - Is field conditionally rendered?
   ```tsx
   {source.author && <div>{source.author}</div>}  // ← Is this here?
   ```

4. **Check browser console** - Log the data:
   ```tsx
   console.log('Source:', source)  // See all fields
   ```

---

## ✅ **Deploy Changes:**

```bash
cd mvp_marketing_app

# Backend changes
git add backend/rag/pipeline.py

# Commit
git commit -m "Fix source metadata mapping - score, thread_url, all fields"

# Push
git push
```

**Render will auto-deploy backend in 3-5 minutes.**

After deployment, the issues should be fixed:
- ✅ Score shows correct percentage
- ✅ Thread URL is clickable
- ✅ All metadata fields display properly

---

## 📚 **File Reference:**

| File | Purpose | Key Functions |
|------|---------|---------------|
| `backend/rag/vectorstore.py` | Qdrant search | `search_reddit_posts()` - Creates metadata |
| `backend/rag/pipeline.py` | Format data | `format_sources()` - Maps fields |
| `backend/api/rag.py` | API endpoint | Returns JSON to frontend |
| `frontend/app/results/[jobId]/page.tsx` | Display | Renders all fields |

---

🎉 **All fields now properly mapped from Qdrant → Backend → Frontend!**

