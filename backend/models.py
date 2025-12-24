from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

Base = declarative_base()


# SQLAlchemy Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_subscribed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    template = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    status = Column(String, default="completed")
    refined_text = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False)
    retrieved_docs = Column(JSON, nullable=True)  # Store the retrieved documents for frontend
    final_prompt = Column(Text, nullable=True)  # Store the final prompt used by LLM
    original_request = Column(Text, nullable=True)  # Store the original marketing text
    topics = Column(JSON, nullable=True)  # Store the selected topics/backgrounds
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    is_subscribed: bool = False


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    is_subscribed: bool
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PromptTemplateRequest(BaseModel):
    template: str


class PromptTemplateResponse(BaseModel):
    template: str


class RAGProcessRequest(BaseModel):
    backgrounds: List[str]
    marketing_text: str
    asset_type: Optional[str] = None
    icp: Optional[str] = None
    template_override: Optional[str] = None


class RAGProcessResponse(BaseModel):
    job_id: str


class SourceItem(BaseModel):
    doc_id: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
    snippet: Optional[str] = None
    score: Optional[float] = 0.0
    # Source type fields
    source: Optional[str] = None
    source_type: Optional[str] = None
    doc_type: Optional[str] = None
    file_id: Optional[int] = None
    text: Optional[str] = None
    
    # Common fields across all document types (new structure)
    citation: Optional[str] = None
    citation_start_time: Optional[float] = None
    icp_role_type: Optional[str] = None
    title: Optional[str] = None
    channel: Optional[str] = None
    type: Optional[str] = None
    
    # Podcast-specific fields
    episode_url: Optional[str] = None
    episode_number: Optional[int] = None
    mp3_url: Optional[str] = None
    
    # Reddit-specific fields
    selftext: Optional[str] = None
    thread_author: Optional[str] = None
    subreddit: Optional[str] = None
    thread_url: Optional[str] = None
    detailed_explanation: Optional[str] = Field(None, alias='detailed-explanation')
    
    # YouTube-specific fields
    video_url: Optional[str] = None
    description: Optional[str] = None
    
    # Legacy fields (for backward compatibility)
    author: Optional[str] = None
    author_fullname: Optional[str] = None
    comment_url: Optional[str] = None
    parent_comment_url: Optional[str] = None
    thread_index: Optional[int] = None
    reply_index: Optional[int] = None
    flair_text: Optional[str] = None
    ups: Optional[int] = None
    timestamp: Optional[str] = None
    created_utc: Optional[str] = None
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    level: Optional[int] = None
    
    class Config:
        populate_by_name = True


class RAGResultResponse(BaseModel):
    job_id: str
    refined_text: str
    sources: List[SourceItem]
    retrieved_docs: List[Dict[str, Any]] = []
    final_prompt: Optional[str] = None
    original_request: Optional[str] = None
    topics: Optional[List[str]] = None
