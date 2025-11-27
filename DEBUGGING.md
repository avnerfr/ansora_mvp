# Debugging Guide - Marketing MVP Backend

## 📋 Overview

The backend now has comprehensive logging throughout the RAG pipeline to help you debug issues.

## 🔍 Viewing Logs

### View Real-Time Logs (Follow Mode)
```bash
cd mvp_marketing_app
docker-compose logs backend -f
```
This will show logs as they happen in real-time. Press `Ctrl+C` to stop.

### View Last N Lines
```bash
# Last 50 lines
docker-compose logs backend --tail 50

# Last 100 lines
docker-compose logs backend --tail 100
```

### View Logs for Specific Time Range
```bash
# Logs since a specific time
docker-compose logs backend --since 2023-11-27T10:00:00

# Logs in the last 10 minutes
docker-compose logs backend --since 10m
```

### Search Logs for Specific Text
```bash
# On Windows PowerShell
docker-compose logs backend | Select-String "ERROR"
docker-compose logs backend | Select-String "RAG Pipeline"

# On Linux/Mac
docker-compose logs backend | grep "ERROR"
docker-compose logs backend | grep "RAG Pipeline"
```

### View All Service Logs
```bash
docker-compose logs -f
```

## 📊 Log Levels

Logs are structured with different levels:

- **INFO**: Normal operation, progress updates
- **WARNING**: Potential issues, but operation continues
- **ERROR**: Errors that need attention
- **DEBUG**: Detailed information for deep debugging

## 🔎 What's Logged

### 1. API Endpoint (`/api/v1/rag/process`)
- Request received with user info
- Validation results
- Template selection (custom/default/override)
- RAG pipeline call
- Job creation and database save
- Final response

### 2. RAG Pipeline (`rag/pipeline.py`)
- User ID and request parameters
- Document retrieval from Qdrant
- Number of documents retrieved
- Details of each retrieved document
- Context building
- Prompt construction
- LLM (GPT-4) initialization
- LLM API call and response
- Source formatting
- Final output

### 3. Example Log Flow

```
2025-11-27 10:15:23 - api.rag - INFO - POST /api/v1/rag/process - User: user@example.com (ID: 1)
2025-11-27 10:15:23 - api.rag - INFO - Request validated - Backgrounds: ['Healthcare'], Text length: 245
2025-11-27 10:15:23 - api.rag - INFO - Using default template
2025-11-27 10:15:23 - api.rag - INFO - Calling RAG pipeline...
2025-11-27 10:15:23 - rag.pipeline - INFO - === Starting RAG Pipeline ===
2025-11-27 10:15:23 - rag.pipeline - INFO - User ID: 1
2025-11-27 10:15:23 - rag.pipeline - INFO - Backgrounds: ['Healthcare']
2025-11-27 10:15:23 - rag.pipeline - INFO - Marketing text length: 245 chars
2025-11-27 10:15:23 - rag.pipeline - INFO - Retrieving relevant documents from vector store...
2025-11-27 10:15:24 - rag.pipeline - INFO - Retriever created for user_1_documents collection
2025-11-27 10:15:24 - rag.pipeline - INFO - ✓ Retrieved 3 documents
2025-11-27 10:15:24 - rag.pipeline - INFO -   Doc 1: healthcare_guide.pdf (file_id: 42, content length: 850 chars)
2025-11-27 10:15:24 - rag.pipeline - INFO -   Doc 2: marketing_tips.pdf (file_id: 43, content length: 720 chars)
2025-11-27 10:15:24 - rag.pipeline - INFO -   Doc 3: brand_voice.pptx (file_id: 44, content length: 640 chars)
2025-11-27 10:15:24 - rag.pipeline - INFO - Formatting context from retrieved documents...
2025-11-27 10:15:24 - rag.pipeline - INFO - ✓ Context built: 2210 chars from 3 sources
2025-11-27 10:15:24 - rag.pipeline - INFO - Backgrounds string: Healthcare
2025-11-27 10:15:24 - rag.pipeline - INFO - Building final prompt...
2025-11-27 10:15:24 - rag.pipeline - INFO - ✓ Prompt built: 2650 chars
2025-11-27 10:15:24 - rag.pipeline - INFO - Initializing LLM (GPT-4, temp=0.7)...
2025-11-27 10:15:24 - rag.pipeline - INFO - ✓ LLM initialized
2025-11-27 10:15:24 - rag.pipeline - INFO - Sending request to OpenAI API...
2025-11-27 10:15:28 - rag.pipeline - INFO - ✓ LLM response received: 523 chars
2025-11-27 10:15:28 - rag.pipeline - INFO - Formatting sources...
2025-11-27 10:15:28 - rag.pipeline - INFO - ✓ Formatted 3 sources
2025-11-27 10:15:28 - rag.pipeline - INFO - === RAG Pipeline Completed Successfully ===
2025-11-27 10:15:28 - api.rag - INFO - ✓ RAG pipeline completed - Output: 523 chars, Sources: 3
2025-11-27 10:15:28 - api.rag - INFO - Generated job_id: abc-123-def-456
2025-11-27 10:15:28 - api.rag - INFO - ✓ Job saved to database
2025-11-27 10:15:28 - api.rag - INFO - ✓ Request completed successfully - job_id: abc-123-def-456
```

## 🐛 Common Issues to Look For

### 1. No Documents Retrieved
```
⚠ Retrieved 0 documents
```
**Cause**: User hasn't uploaded any documents yet, or documents aren't in Qdrant.
**Solution**: Upload documents via `/api/v1/documents/upload`

### 2. Vector Store Error
```
⚠ Error retrieving documents: QdrantException: Collection not found
```
**Cause**: User's collection doesn't exist in Qdrant.
**Solution**: Upload documents to create the collection automatically.

### 3. OpenAI API Error
```
✗ Error calling LLM: AuthenticationError: Invalid API key
```
**Cause**: `OPENAI_API_KEY` is missing or invalid.
**Solution**: Check `.env` file and restart backend.

### 4. Empty Context
```
Context built: 34 chars from 0 sources
```
**Cause**: Query didn't match any documents (low similarity).
**Solution**: Upload more relevant documents or improve query.

## 🔧 Debugging Tips

### 1. Enable DEBUG Level Logging

Edit `rag/pipeline.py` line 14:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

This will show:
- Full marketing text
- Full template
- Full prompt sent to LLM
- Detailed context parts

### 2. Rebuild Backend After Changes

```bash
cd mvp_marketing_app
docker-compose build backend --no-cache
docker-compose up backend -d
```

### 3. Check Environment Variables

```bash
docker-compose exec backend env | grep OPENAI
docker-compose exec backend env | grep QDRANT
```

### 4. Test Qdrant Connection

```bash
# Check if Qdrant is running
docker-compose ps qdrant

# Check collections
docker-compose exec backend python -c "
from qdrant_client import QdrantClient
from core.config import settings
client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
print(client.get_collections())
"
```

### 5. Check Database

```bash
# List all jobs
docker-compose exec backend python -c "
from db import SessionLocal
from models import Job
db = SessionLocal()
jobs = db.query(Job).all()
for job in jobs:
    print(f'Job {job.job_id}: {job.status}, user_id={job.user_id}')
"
```

## 📁 Log File Locations

Logs are written to:
- **stdout**: Captured by Docker (use `docker-compose logs`)
- **Container logs**: `/var/log/` (inside container)

To save logs to a file:
```bash
docker-compose logs backend > backend_logs.txt
```

## 🚀 Performance Monitoring

Track timing in logs:
- Document retrieval time
- LLM response time
- Total request time

Look for slow operations:
```bash
docker-compose logs backend | Select-String "Sending request to OpenAI"
docker-compose logs backend | Select-String "LLM response received"
```

## 💡 Pro Tips

1. **Keep logs open in a separate terminal** while testing
2. **Use timestamps** to correlate frontend actions with backend logs
3. **Search for job_id** to track a specific request through the entire pipeline
4. **Look for checkmarks (✓) and X marks (✗)** for quick success/failure identification
5. **Check for warnings (⚠)** that might indicate non-critical issues

## 🔗 Related Files

- `backend/api/rag.py` - API endpoint logging
- `backend/rag/pipeline.py` - RAG pipeline logging
- `backend/rag/vectorstore.py` - Vector store operations
- `backend/rag/loader.py` - Document loading

