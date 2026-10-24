"""Register, log in, and find the user behind a token."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AuthError, ConflictError
from app.db import repository
from app.db.models import User


def register(db: Session, username: str, password: str) -> User:
    if repository.get_user_by_username(db, username):
        raise ConflictError("That username is already taken.")
    try:
        return repository.create_user(db, username, security.hash_password(password))
    except IntegrityError:
        db.rollback()
        raise ConflictError("That username is already taken.")


def login(db: Session, username: str, password: str) -> str:
    user = repository.get_user_by_username(db, username.strip())
    if user is None or not security.verify_password(password, user.password_hash):
        raise AuthError("Wrong username or password.")
    return security.create_access_token(user.id)


def user_from_token(db: Session, token: str) -> User:
    user_id = security.decode_access_token(token)
    user = repository.get_user(db, user_id) if user_id is not None else None
    if user is None:
        raise AuthError("Not logged in, or the login has expired.")
    return user
