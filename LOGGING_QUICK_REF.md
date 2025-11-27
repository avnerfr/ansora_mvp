# 🔍 Logging Quick Reference

## View Logs in Real-Time

```bash
cd mvp_marketing_app
docker-compose logs backend -f
```

**Now when you make a request to `/api/v1/rag/process`, you'll see detailed logs like:**

## 📊 Example Log Output

```
# 1. Request arrives
2025-11-27 10:15:23 - api.rag - INFO - POST /api/v1/rag/process - User: user@example.com (ID: 1)
2025-11-27 10:15:23 - api.rag - INFO - Request validated - Backgrounds: ['Healthcare'], Text length: 245

# 2. Template selection
2025-11-27 10:15:23 - api.rag - INFO - Using default template

# 3. RAG Pipeline starts
2025-11-27 10:15:23 - rag.pipeline - INFO - === Starting RAG Pipeline ===
2025-11-27 10:15:23 - rag.pipeline - INFO - User ID: 1
2025-11-27 10:15:23 - rag.pipeline - INFO - Backgrounds: ['Healthcare']
2025-11-27 10:15:23 - rag.pipeline - INFO - Marketing text length: 245 chars

# 4. Vector search
2025-11-27 10:15:24 - rag.pipeline - INFO - Retrieving relevant documents from vector store...
2025-11-27 10:15:24 - rag.pipeline - INFO - ✓ Retrieved 3 documents
2025-11-27 10:15:24 - rag.pipeline - INFO -   Doc 1: healthcare_guide.pdf (file_id: 42, content length: 850 chars)
2025-11-27 10:15:24 - rag.pipeline - INFO -   Doc 2: marketing_tips.pdf (file_id: 43, content length: 720 chars)

# 5. Context building
2025-11-27 10:15:24 - rag.pipeline - INFO - ✓ Context built: 2210 chars from 3 sources

# 6. LLM call
2025-11-27 10:15:24 - rag.pipeline - INFO - Initializing LLM (GPT-4, temp=0.7)...
2025-11-27 10:15:24 - rag.pipeline - INFO - Sending request to OpenAI API...
2025-11-27 10:15:28 - rag.pipeline - INFO - ✓ LLM response received: 523 chars

# 7. Results saved
2025-11-27 10:15:28 - api.rag - INFO - ✓ Job saved to database
2025-11-27 10:15:28 - api.rag - INFO - ✓ Request completed successfully - job_id: abc-123-def-456
```

## 🎯 Quick Commands

### View last 50 lines
```bash
docker-compose logs backend --tail 50
```

### Search for errors
```bash
# PowerShell
docker-compose logs backend | Select-String "ERROR"
docker-compose logs backend | Select-String "✗"

# Linux/Mac
docker-compose logs backend | grep "ERROR"
docker-compose logs backend | grep "✗"
```

### Search for specific job
```bash
docker-compose logs backend | Select-String "abc-123-def-456"
```

### View only RAG pipeline logs
```bash
docker-compose logs backend | Select-String "rag.pipeline"
```

## 📍 What Gets Logged

### ✅ Success Indicators
- `✓` - Operation succeeded
- `INFO` - Normal operation

### ⚠️ Warning Indicators
- `⚠` - Non-critical issues
- `WARNING` - Warnings

### ❌ Error Indicators
- `✗` - Operation failed
- `ERROR` - Errors

## 🐛 Common Debug Patterns

### Check if documents are being retrieved
```bash
docker-compose logs backend | Select-String "Retrieved.*documents"
```

### Check LLM timing
```bash
docker-compose logs backend | Select-String "Sending request to OpenAI"
docker-compose logs backend | Select-String "LLM response received"
```

### Track a specific user's requests
```bash
docker-compose logs backend | Select-String "User ID: 1"
```

## 📝 Adding More Logs

To add custom logs in your code:

```python
import logging
logger = logging.getLogger(__name__)

# Different log levels
logger.debug("Detailed debug info")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)  # Include stack trace
```

## 🔧 Enable DEBUG Mode

Edit `backend/rag/pipeline.py` line 14:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

Then rebuild:
```bash
docker-compose build backend
docker-compose up backend -d
```

