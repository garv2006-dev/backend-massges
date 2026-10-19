"""JSON Web Token (JWT) Security and Authentication Module.

Handles cryptographically secure JWT issuance, signature verification, and 7-day expiration.
"""

from datetime import datetime, timedelta
from typing import Union, Any, Optional
from jose import jwt, JWTError
from app.config import settings

ALGORITHM = settings.ALGORITHM

# 7 days in minutes: 7 * 24 * 60 = 10,080 minutes
SEVEN_DAYS_MINUTES = 7 * 24 * 60


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a cryptographically signed JWT access token.
    Defaults to 7 days (10,080 minutes) validity for seamless user experience in production.
    """
    now = datetime.utcnow()
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire_minutes = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", SEVEN_DAYS_MINUTES) or SEVEN_DAYS_MINUTES
        expire = now + timedelta(minutes=expire_minutes)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": str(subject),
        "type": "access_token"
    }

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """
    Decode and verify a JWT access token.
    Returns user subject ID if valid, or None if expired or signature is invalid.
    """
    if not token or not isinstance(token, str):
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        return user_id
    except JWTError:
        return None
