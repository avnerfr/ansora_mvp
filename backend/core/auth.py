from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt, jwk
from jose.utils import base64url_decode
import bcrypt
import httpx
import json
import base64
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from core.config import settings
from db import get_db
from models import User
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Cognito configuration - using settings from config
COGNITO_ISSUER = f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/{settings.COGNITO_USER_POOL_ID}"
COGNITO_JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"

# Cache for JWKS keys
_jwks_cache = None


async def get_cognito_jwks():
    """Fetch and cache Cognito JWKS keys."""
    global _jwks_cache
    if _jwks_cache is None:
        logger.info(f"Fetching JWKS from: {COGNITO_JWKS_URL}")
        async with httpx.AsyncClient() as client:
            response = await client.get(COGNITO_JWKS_URL)
            response.raise_for_status()
            _jwks_cache = response.json()
            logger.info(f"✓ JWKS fetched successfully. Found {len(_jwks_cache.get('keys', []))} keys")
    return _jwks_cache


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hash a password."""
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user from Cognito JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        
        # Get the key id from the token header
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        
        if not kid:
            logger.error("No kid in token header")
            raise credentials_exception
        
        # Get JWKS and find the matching key
        jwks = await get_cognito_jwks()
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == kid:
                key = k
                break
        
        if not key:
            logger.error(f"Key {kid} not found in JWKS from {COGNITO_JWKS_URL}")
            logger.error(f"Available keys in JWKS: {[k.get('kid') for k in jwks.get('keys', [])]}")
            logger.error(f"Expected issuer: {COGNITO_ISSUER}")
            logger.error(f"Configured User Pool: {settings.COGNITO_USER_POOL_ID} in region {settings.COGNITO_REGION}")
            
            # Try to decode token (unverified) to get issuer info
            try:
                # Decode token header
                header_data = token.split('.')[0]
                header_data += '=' * (4 - len(header_data) % 4)  # Add padding
                header = json.loads(base64.urlsafe_b64decode(header_data))
                logger.error(f"Token header: {header}")
                
                # Decode payload (unverified) to get issuer
                payload_data = token.split('.')[1]
                payload_data += '=' * (4 - len(payload_data) % 4)  # Add padding
                payload_unverified = json.loads(base64.urlsafe_b64decode(payload_data))
                logger.error(f"Token issuer (unverified): {payload_unverified.get('iss')}")
                logger.error(f"Token sub: {payload_unverified.get('sub')}")
                logger.error(f"Token exp: {payload_unverified.get('exp')}")
            except Exception as e:
                logger.error(f"Could not decode token: {e}")
            
            # Clear cache to force refresh on next request
            global _jwks_cache
            _jwks_cache = None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: Key ID mismatch. Token may be from a different User Pool or expired. "
                       f"Configured: {settings.COGNITO_REGION}/{settings.COGNITO_USER_POOL_ID}"
            )
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=None,  # Cognito access tokens don't have aud claim
            issuer=COGNITO_ISSUER,
            options={"verify_aud": False}
        )
        
        # Get user email from token
        email = payload.get("email") or payload.get("username")
        cognito_sub = payload.get("sub")
        
        if not email and not cognito_sub:
            logger.error("No email or sub in token")
            raise credentials_exception
        
        logger.info(f"Cognito user authenticated: {email or cognito_sub}")
        
        # Find or create user in database
        user = None
        if email:
            user = db.query(User).filter(User.email == email).first()
        
        if not user and cognito_sub:
            # Try to find by cognito_sub if we store it, or create new user
            user = db.query(User).filter(User.email == email).first() if email else None
        
        if not user:
            # Auto-create user from Cognito
            logger.info(f"Creating new user from Cognito: {email}")
            user = User(
                email=email or f"{cognito_sub}@cognito.user",
                hashed_password="cognito_managed",  # Not used for Cognito users
                is_subscribed=False,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        return user
        
    except JWTError as e:
        logger.error(f"JWT validation error: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise credentials_exception
