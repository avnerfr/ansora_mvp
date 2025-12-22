# Debugging "No Sources" Issue

## ✅ Fixes Applied

### 1. **Embedding Model Mismatch Fixed**
- Added auto-detection of collection vector size (384 or 1536)
- Uses SentenceTransformer for 384D collections
- Uses OpenAI embeddings for 1536D collections

### 2. **Error Handling Improved**
- Added try-catch blocks around collection info access
- Added error handling for SentenceTransformer initialization
- Added validation for vector size matching
- Added error handling in results endpoint

### 3. **Collection Name Priority**
- Prioritizes `reddit_posts` collection
- Falls back to `reddit_yt_posts` if needed

## 🔍 Debugging Steps

### Step 1: Rebuild Docker Container

The Docker container needs to be rebuilt to include `sentence-transformers`:

```powershell
cd mvp_marketing_app
docker-compose down
docker-compose build --no-cache backend
docker-compose up -d
```

### Step 2: Check Backend Logs

Watch the logs to see what's happening:

```powershell
docker-compose logs -f backend
```

Look for:
- "✓ SentenceTransformer initialized: 384D" - confirms model loaded
- "✓ Found reddit_posts collection" - confirms collection found
- "Collection info: X points, 384D vectors" - confirms collection has data
- "✓ Query vector generated: 384D" - confirms embedding created
- "✓ Search completed: X results" - shows how many results found

### Step 3: Verify Collection Has Data

Check if the collection actually has points:

```python
from qdrant_client import QdrantClient
from dotenv import load_dotenv
# Initialize clients
load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

collection_info = client.get_collection("reddit_posts")
print(f"Points: {collection_info.points_count}")
print(f"Vector size: {collection_info.config.params.vectors.size}")
```

### Step 4: Test Search Directly

Test if search works:

```python
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from dotenv import load_dotenv
# Initialize clients
load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

query = "security updates"
query_vector = model.encode(query).tolist()

results = client.query_points(
    collection_name="reddit_posts",
    query=query_vector,
    limit=5,
    with_payload=True
)

print(f"Found {len(results.points)} results")
for point in results.points:
    print(f"Score: {point.score}, Text: {point.payload.get('text', '')[:100]}")
```

## 🐛 Common Issues

### Issue: "SentenceTransformer not initialized"
**Solution:** Rebuild Docker container to install sentence-transformers

### Issue: "Collection not found"
**Solution:** Check collection name - might be `reddit_yt_posts` instead

### Issue: "Vector size mismatch"
**Solution:** Collection was created with wrong vector size. Need to recreate collection with correct size (384D for SentenceTransformer)

### Issue: "No results found"
**Possible causes:**
1. Collection is empty (0 points)
2. Query doesn't match any documents
3. Search is working but returning low similarity scores

## 📝 Next Steps

1. **Rebuild Docker container** with updated code
2. **Check logs** for detailed error messages
3. **Verify collection** has data
4. **Test search** directly to isolate the issue

