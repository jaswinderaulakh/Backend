"""Shared pieces for the route files: who is logged in."""
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import accounts
from app.core.errors import ForbiddenError
from app.db.models import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    return accounts.user_from_token(db, token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise ForbiddenError("Administrator access is required for this action.")
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
