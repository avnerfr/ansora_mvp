import os
from dataclasses import dataclass, field


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
            "https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333",
        )
    )
    QDRANT_API_KEY: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    ALLOWED_ORIGINS: str = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"))
    STORAGE_PATH: str = field(default_factory=lambda: os.getenv("STORAGE_PATH", "./storage"))
    # Cognito configuration for JWT verification
    COGNITO_REGION: str = field(default_factory=lambda: os.getenv("COGNITO_REGION", "eu-north-1"))
    COGNITO_USER_POOL_ID: str = field(default_factory=lambda: os.getenv("COGNITO_USER_POOL_ID", "eu-north-1_sa160lFGQ"))


settings = Settings()


