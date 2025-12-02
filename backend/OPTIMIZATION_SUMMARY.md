# Docker Image Optimization Summary

## Major Changes to Reduce Memory Usage

### 1. Removed OpenAI Embeddings (~100-200MB saved)
- **Removed**: `OpenAIEmbeddings` for user documents
- **Replaced with**: `SentenceTransformer` (same model as cloud Qdrant)
- **Impact**: 
  - No OpenAI API calls for embeddings (cost savings)
  - Single model instance shared between user docs and cloud data
  - Reduced memory footprint
- **Code changes**: 
  - Created `SentenceTransformerEmbeddings` wrapper for LangChain compatibility
  - Changed user document vector size from 1536D → 384D
  - Shared model instance to avoid loading twice

### 2. Removed Heavy Dependencies

#### Removed `unstructured[ppt]` (~1-2GB)
- Replaced with lightweight `python-pptx`
- PowerPoint files still supported

#### Removed OCR Dependencies (~50-100MB)
- Removed: `pytesseract`, `pillow`, `tesseract-ocr`
- Images return placeholder text (graceful degradation)

#### Removed PyTorch Extras (~500MB)
- Only install `torch` (removed `torchvision`, `torchaudio`)
- CPU-only PyTorch (no CUDA)

#### Removed LangChain Meta-Package
- Removed `langchain==0.2.16` (meta-package)
- Use specific packages: `langchain-core`, `langchain-community`, `langchain-openai`

#### Removed Pydantic Email Extra
- Changed `pydantic[email]` → `pydantic`
- Saves ~10-20MB

#### Removed Uvicorn Extras
- Changed `uvicorn[standard]` → `uvicorn`
- Saves ~10-20MB (removes uvloop, httptools)

### 3. Memory Optimizations

#### Single Shared Model Instance
- User documents and cloud Qdrant share the same `SentenceTransformer` model
- Prevents loading the model twice (saves ~200MB RAM)
- Lazy-loaded only when needed

#### Lazy Loading
- SentenceTransformer loads only on first use
- Reduces startup memory from ~500MB → ~200-300MB

### 4. Build Optimizations

#### Multi-Stage Docker Build
- Separates build and runtime stages
- Final image excludes build tools

#### System Package Optimizations
- Uses `--no-install-recommends` for apt-get
- Removed unnecessary system packages
- Added `apt-get clean` to remove package lists

## Expected Results

### Image Size
- **Before**: ~4.33GB
- **After**: ~600-800MB (80-85% reduction)

### Memory Usage
- **Startup**: ~200-300MB (down from ~500MB+)
- **After first query**: ~400-500MB (model loaded)
- **Peak**: ~500-600MB (during processing)

### Build Memory
- Should fit within 512MB limit on Render
- Multi-stage build reduces peak memory usage

## Trade-offs

### Functionality Preserved
- ✅ PDF processing (pypdf)
- ✅ PowerPoint processing (python-pptx)
- ✅ User document embeddings (SentenceTransformer)
- ✅ Cloud Qdrant search (SentenceTransformer)
- ✅ LLM processing (ChatOpenAI - still uses OpenAI)

### Functionality Removed/Optional
- ❌ Image OCR (returns placeholder text)
- ⚠️ User documents now use 384D vectors (was 1536D)
  - Existing 1536D collections will need to be re-indexed
  - Or handle both sizes gracefully

## Migration Notes

### For Existing Deployments
1. **User document collections**: If you have existing user documents with 1536D vectors, you'll need to:
   - Option A: Re-index all documents (recommended)
   - Option B: Keep both embedding models (not recommended - uses more memory)

2. **First request will be slower**: The SentenceTransformer model loads on first use (~2-3 seconds)

3. **Memory monitoring**: Monitor memory usage on first few requests to ensure it stays within limits

## Files Changed

- `rag/vectorstore.py` - Replaced OpenAI embeddings with SentenceTransformer
- `rag/loader.py` - Made OCR and PPTX optional
- `requirements.txt` - Removed heavy dependencies
- `Dockerfile` - Multi-stage build, CPU-only PyTorch
- `.dockerignore` - Enhanced exclusions

## Next Steps if Still Having Issues

1. **Further reduce model size**: Use a smaller embedding model (e.g., `all-MiniLM-L6-v2` is already small, but could try `paraphrase-MiniLM-L3-v2`)

2. **Disable user document uploads**: If not needed, remove that feature entirely

3. **Use external embedding service**: Offload embeddings to an external API

4. **Upgrade Render plan**: If budget allows, upgrade to a plan with more memory

