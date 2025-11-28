from importlib import import_module
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
from api import auth, documents, rag

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
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"])


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

