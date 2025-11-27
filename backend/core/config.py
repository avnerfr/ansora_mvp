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
    QDRANT_URL: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://qdrant:6333"))
    QDRANT_API_KEY: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    ALLOWED_ORIGINS: str = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"))
    STORAGE_PATH: str = field(default_factory=lambda: os.getenv("STORAGE_PATH", "./storage"))


settings = Settings()


