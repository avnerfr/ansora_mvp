from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db import get_db, init_db
from models import User, UserCreate, UserLogin, UserResponse, TokenResponse
from core.auth import verify_password, get_password_hash, create_access_token, get_current_user
from rag.vectorstore import vector_store
from core.config import settings
import logging
import os
import shutil

router = APIRouter()
logger = logging.getLogger(__name__)


def clear_user_data(user_id: int, db: Session):
    """
    Clear all user data: Qdrant collection and any stored files.
    Note: We no longer persist uploaded documents in the database.
    """
    logger.info(f"Clearing all data for user {user_id}")
    
    # 1. Clear Qdrant collection
    try:
        vector_store.clear_user_collection(user_id)
        logger.info(f"✓ Cleared Qdrant collection for user {user_id}")
    except Exception as e:
        logger.error(f"✗ Failed to clear Qdrant collection: {str(e)}")
    
    # 2. Delete uploaded files from filesystem
    try:
        user_storage_dir = os.path.join(settings.STORAGE_PATH, str(user_id))
        if os.path.exists(user_storage_dir):
            shutil.rmtree(user_storage_dir)
            logger.info(f"✓ Deleted storage directory for user {user_id}")
        else:
            logger.info(f"No storage directory found for user {user_id}")
    except Exception as e:
        logger.error(f"✗ Failed to delete storage directory: {str(e)}")
    
@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        is_subscribed=user_data.is_subscribed
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Clear any existing data for this user (in case of re-registration)
    logger.info(f"Clearing all data for new user {new_user.id} ({new_user.email})")
    clear_user_data(new_user.id, db)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})
    
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login and get access token."""
    user = db.query(User).filter(User.email == user_data.email).first()
    
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Clear all user data on login (Qdrant, files, database records)
    logger.info(f"Clearing all data for user {user.id} ({user.email}) on login")
    clear_user_data(user.id, db)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(id=current_user.id, email=current_user.email, is_subscribed=current_user.is_subscribed)

