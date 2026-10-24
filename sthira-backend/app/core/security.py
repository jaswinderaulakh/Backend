"""Password hashing and login tokens."""
from datetime import timedelta
from typing import Optional

import bcrypt
import jwt

from app.core.clock import utcnow
from app.core.settings import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    expires = utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[int]:
    """Return the user id inside a valid token, or None if the token is bad or expired."""
    settings = get_settings()
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
