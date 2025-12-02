# Docker Build Optimization

## Problem
The Docker build was running out of memory (512MB limit on Render) due to:
- Large PyTorch dependencies (~4.33GB layer)
- Heavy `unstructured[ppt]` library (~1-2GB)
- SentenceTransformer loading at startup
- Unnecessary dependencies (torchvision, torchaudio, OCR tools)
- No build optimizations

## Solutions Implemented

### 1. Multi-Stage Docker Build
- **Builder stage**: Installs build dependencies and compiles Python packages
- **Runtime stage**: Only includes runtime dependencies, significantly smaller final image
- Reduces final image size by excluding build tools (gcc, g++, etc.)
- Uses `--no-install-recommends` to avoid unnecessary packages

### 2. CPU-Only PyTorch (Minimal)
- Installs CPU-only PyTorch (~2GB smaller than CUDA version)
- **Only installs `torch`** (removed `torchvision` and `torchaudio` - saves ~500MB)
- Prevents `sentence-transformers` from pulling full CUDA-enabled PyTorch
- Installed before other requirements to ensure correct version

### 3. Removed Heavy Dependencies

#### Removed `unstructured[ppt]` (~1-2GB)
- **Replaced with**: Lightweight `python-pptx` (already in requirements)
- **Impact**: Saves ~1-2GB
- **Functionality**: PowerPoint files still supported via direct `python-pptx` usage

#### Removed OCR Dependencies (Optional)
- **Removed**: `pytesseract`, `pillow`, `tesseract-ocr`, `libtesseract-dev`
- **Impact**: Saves ~50-100MB
- **Functionality**: OCR gracefully degrades - images return placeholder text
- **Note**: Can be re-enabled if OCR is needed

#### Removed uvicorn[standard] extras
- **Changed**: `uvicorn[standard]` → `uvicorn`
- **Impact**: Saves ~10-20MB (removes uvloop, httptools optional deps)
- **Functionality**: Still works, just without performance optimizations

### 4. Lazy Loading of SentenceTransformer
- Changed from eager initialization to lazy loading via `@property`
- Model only loads when actually needed (during RAG queries)
- Reduces startup memory usage significantly

### 5. Enhanced .dockerignore File
- Excludes unnecessary files from build context:
  - Python cache files (`__pycache__/`, `*.pyc`)
  - Virtual environments (`venv/`, `env/`)
  - IDE files (`.vscode/`, `.idea/`)
  - Documentation (`*.md`, `docs/`)
  - Git files (`.git/`)
  - Local storage (`storage/`, `db/`)
  - Test files and data files
  - Build artifacts

### 6. Build Optimizations
- Added `--no-install-recommends` to apt-get (reduces system package size)
- Added `apt-get clean` to remove package lists
- Removed pip cache after installation
- Combined RUN commands where possible

## Expected Results
- **Image size**: Reduced from ~4.33GB to **~800MB-1.2GB** (70-80% reduction)
- **Build memory**: Lower peak memory usage during build
- **Startup memory**: Reduced from ~500MB+ to ~200-300MB (until first RAG query)
- **Build time**: Slightly longer due to multi-stage, but more reliable

## Size Breakdown (Estimated)
- Base Python slim: ~150MB
- PyTorch (CPU-only, torch only): ~500MB
- Sentence-transformers + model: ~200MB
- LangChain + dependencies: ~100MB
- FastAPI + other Python packages: ~50MB
- System dependencies: ~50MB
- **Total: ~1.05GB** (down from 4.33GB)

## Deployment Notes
- The first RAG query that uses SentenceTransformer will take longer (model loading)
- Subsequent queries will be fast (model cached in memory)
- PowerPoint files: Still supported via `python-pptx` (lighter than unstructured)
- Image OCR: Not available (returns placeholder). Re-enable if needed.
- If memory is still an issue, consider:
  - Upgrading Render plan (more memory)
  - Using a smaller embedding model
  - Offloading model to external service
  - Further removing optional features

