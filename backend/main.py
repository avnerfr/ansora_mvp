from importlib import import_module
from dotenv import load_dotenv
import os
import sys
import logging
from pathlib import Path

# Configure logging at app startup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Load environment variables from .env file in backend directory
backend_dir = Path(__file__).parent
env_path = backend_dir / ".env"
load_dotenv(dotenv_path=env_path)

from core.config import settings  # adjust import if your path is different

try:
    FastAPI = import_module("fastapi").FastAPI  # type: ignore[attr-defined]
    CORSMiddleware = import_module("fastapi.middleware.cors").CORSMiddleware  # type: ignore[attr-defined]
except ModuleNotFoundError as exc:  # pragma: no cover - fail fast when dependency missing
    raise ImportError(
        "FastAPI is required to run the backend API. Install it with "
        "`pip install fastapi uvicorn`."
    ) from exc
from core.config import settings
from db import init_db
from api import auth, rag, maintenance

# Initialize database
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Ansora - RAG-powered marketing material refinement",
    version="1.0.0"
)

# Parse ALLOWED_ORIGINS from comma-separated string to list
origins = [
    origin.strip()
    for origin in settings.ALLOWED_ORIGINS.split(",")
    if origin.strip()
]

# Debug logging
import logging
import json
from logging.config import dictConfig
from pathlib import Path

# Load and configure logging from JSON config to prevent duplicates
config_path = Path(__file__).parent / "logging_config.json"
if config_path.exists():
    with open(config_path) as f:
        log_config = json.load(f)
    dictConfig(log_config)

logger = logging.getLogger(__name__)
logger.info(f"🔍 ALLOWED_ORIGINS env var: {settings.ALLOWED_ORIGINS}")
logger.info(f"🔍 Parsed origins list: {origins}")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"✅ CORS middleware configured with {len(origins)} origins")

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"])
app.include_router(maintenance.router, prefix="/api/v1/maintenance", tags=["maintenance"])


@app.get("/")
async def root():
    return {"message": "Ansora API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/debug/cors")
async def debug_cors():
    """Debug endpoint to check CORS configuration."""
    return {
        "allowed_origins_env": settings.ALLOWED_ORIGINS,
        "parsed_origins": origins,
        "origins_count": len(origins),
        "cors_configured": len(origins) > 0
    }


if __name__ == "__main__":
    uvicorn = import_module("uvicorn")  # type: ignore[assignment]
    uvicorn.run(app, host="0.0.0.0", port=8000)

