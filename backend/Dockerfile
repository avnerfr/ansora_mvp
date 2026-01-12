# Multi-stage build to reduce final image size
FROM python:3.12-slim as builder

WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install CPU-only PyTorch first to reduce image size (no CUDA dependencies ~2GB smaller)
# Only install torch (not torchvision/torchaudio) - saves ~500MB
# This prevents sentence-transformers from pulling the full CUDA-enabled PyTorch
RUN pip install --no-cache-dir --user --index-url https://download.pytorch.org/whl/cpu torch

# Install Python dependencies in a virtual environment
# Use --no-deps for packages that might pull unnecessary extras
RUN pip install --no-cache-dir --user -r requirements.txt

# Download NLTK data needed for sentence tokenization
RUN python -c "import nltk; nltk.download('punkt')"

# Clean up pip cache and temporary files
RUN rm -rf /root/.cache/pip

# Final stage - minimal runtime image
FROM python:3.12-slim

WORKDIR /app

# Install only essential runtime system dependencies
# Removed: tesseract-ocr, libtesseract-dev (OCR is optional, saves ~50MB)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

ENV PYTHONBUFFERED=1

# Copy application code
COPY . .

# Create storage and database directories
RUN mkdir -p storage db

# Expose port (Render will assign this dynamically)
EXPOSE 8000

# Run the application
# Use shell form to allow environment variable expansion
# Use custom log config to prevent duplicate handlers
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --log-config logging_config.json
