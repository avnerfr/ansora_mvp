# Docker Build Optimization

## Problem
The Docker build was running out of memory (512MB limit on Render) due to:
- Large PyTorch dependencies (~4.33GB layer)
- SentenceTransformer loading at startup
- No build optimizations

## Solutions Implemented

### 1. Multi-Stage Docker Build
- **Builder stage**: Installs build dependencies and compiles Python packages
- **Runtime stage**: Only includes runtime dependencies, significantly smaller final image
- Reduces final image size by excluding build tools (gcc, g++, etc.)

### 2. CPU-Only PyTorch
- Installs CPU-only PyTorch (~2GB smaller than CUDA version)
- Prevents `sentence-transformers` from pulling full CUDA-enabled PyTorch
- Installed before other requirements to ensure correct version

### 3. Lazy Loading of SentenceTransformer
- Changed from eager initialization to lazy loading via `@property`
- Model only loads when actually needed (during RAG queries)
- Reduces startup memory usage significantly

### 4. .dockerignore File
- Excludes unnecessary files from build context:
  - Python cache files (`__pycache__/`, `*.pyc`)
  - Virtual environments (`venv/`, `env/`)
  - IDE files (`.vscode/`, `.idea/`)
  - Documentation (`*.md`, `docs/`)
  - Git files (`.git/`)
  - Local storage (`storage/`, `db/`)

## Expected Results
- **Image size**: Reduced from ~4.33GB to ~1-2GB
- **Build memory**: Lower peak memory usage during build
- **Startup memory**: Reduced from ~500MB+ to ~200-300MB (until first RAG query)
- **Build time**: Slightly longer due to multi-stage, but more reliable

## Deployment Notes
- The first RAG query that uses SentenceTransformer will take longer (model loading)
- Subsequent queries will be fast (model cached in memory)
- If memory is still an issue, consider:
  - Upgrading Render plan (more memory)
  - Using a smaller embedding model
  - Offloading model to external service

