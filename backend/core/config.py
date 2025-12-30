import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file in backend directory
# __file__ is: mvp_marketing_app/backend/core/config.py
# parent.parent = mvp_marketing_app/backend
backend_dir = Path(__file__).parent.parent
env_path = backend_dir / ".env"
logger.info(f"Loading .env from: {env_path}")
logger.info(f"Absolute path: {env_path.resolve()}")
logger.info(f".env file exists: {env_path.exists()}")
if not env_path.exists():
    logger.error(f".env file NOT FOUND at: {env_path}")
    logger.error(f"Backend directory: {backend_dir}")
    logger.error(f"Backend directory exists: {backend_dir.exists()}")
    if backend_dir.exists():
        logger.error(f"Files in backend directory: {list(backend_dir.iterdir())}")
load_dotenv(dotenv_path=env_path, override=True)

# Log Qdrant configuration (mask API key for security)
qdrant_url = os.getenv("QDRANT_URL", "")
qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
logger.info(f"QDRANT_URL from env: {qdrant_url}")
if qdrant_api_key:
    # Show first 8 and last 4 characters for verification
    masked_key = f"{qdrant_api_key[:8]}...{qdrant_api_key[-4:]}" if len(qdrant_api_key) > 12 else "***"
    logger.info(f"QDRANT_API_KEY from env: {masked_key} (length: {len(qdrant_api_key)})")
else:
    logger.warning("QDRANT_API_KEY is NOT set in environment")
    # Debug: Check all env vars that start with QDRANT
    qdrant_vars = {k: v for k, v in os.environ.items() if 'QDRANT' in k.upper()}
    logger.warning(f"All QDRANT-related env vars: {list(qdrant_vars.keys())}")
    if qdrant_vars:
        for key, value in qdrant_vars.items():
            if 'KEY' in key:
                masked = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
                logger.warning(f"  {key}: {masked} (length: {len(value)})")
            else:
                logger.warning(f"  {key}: {value}")


@dataclass
class Settings:
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Ansora API"
    JWT_SECRET: str = field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    # Default to the cloud Qdrant endpoint; can be overridden via QDRANT_URL env var.
    QDRANT_URL: str = field(
        default_factory=lambda: os.getenv(
            "QDRANT_URL",
            os.getenv("QDRANT_URL", "https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333"),
        )
    )
    QDRANT_API_KEY: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    ALLOWED_ORIGINS: str = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"))
    STORAGE_PATH: str = field(default_factory=lambda: os.getenv("STORAGE_PATH", "./storage"))
    # Cognito configuration for JWT verification
    COGNITO_REGION: str = field(default_factory=lambda: os.getenv("COGNITO_REGION", "us-east-1"))
    COGNITO_USER_POOL_ID: str = field(default_factory=lambda: os.getenv("COGNITO_USER_POOL_ID", "us-east-1_kOwOgLGdg"))
    DEEPINFRA_API_KEY: str = field(default_factory=lambda: os.getenv("DEEPINFRA_API_KEY", ""))
    DEEPINFRA_API_BASE_URL: str = field(default_factory=lambda: os.getenv("DEEPINFRA_API_BASE_URL", "https://api.deepinfra.com/v1/openai"))


settings = Settings()

# Log settings after creation to verify they were loaded
logger.info("Settings initialized:")
logger.info(f"  QDRANT_URL: {settings.QDRANT_URL}")
if settings.QDRANT_API_KEY:
    masked_key = f"{settings.QDRANT_API_KEY[:8]}...{settings.QDRANT_API_KEY[-4:]}" if len(settings.QDRANT_API_KEY) > 12 else "***"
    logger.info(f"  QDRANT_API_KEY: {masked_key} (length: {len(settings.QDRANT_API_KEY)})")
else:
    logger.warning("  QDRANT_API_KEY: NOT SET in settings object")
    # Debug: Check all env vars that start with QDRANT
    qdrant_vars = {k: v for k, v in os.environ.items() if 'QDRANT' in k.upper()}
    logger.warning(f"  All QDRANT-related env vars in os.environ: {list(qdrant_vars.keys())}")
    if qdrant_vars:
        for key, value in qdrant_vars.items():
            if 'KEY' in key:
                masked = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
                logger.warning(f"    {key}: {masked} (length: {len(value)})")
            else:
                logger.warning(f"    {key}: {value}")


