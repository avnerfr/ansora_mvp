# Multi-stage build to reduce final image size
FROM python:3.12-slim as builder

WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install CPU-only PyTorch first to reduce image size (no CUDA dependencies ~2GB smaller)
# This prevents sentence-transformers from pulling the full CUDA-enabled PyTorch
RUN pip install --no-cache-dir --user --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio

# Install Python dependencies in a virtual environment
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.12-slim

WORKDIR /app

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create storage and database directories
RUN mkdir -p storage db

# Expose port (Render will assign this dynamically)
EXPOSE 8000

# Run the application
# Use shell form to allow environment variable expansion
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
