from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DbSession
from app.core import accounts
from app.core.api_schemas import RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Login"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterRequest, db: DbSession):
    return accounts.register(db, data.username, data.password)


@router.post("/login", response_model=TokenResponse)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession, request: Request):
    """Send `username` and `password` as a form. Returns the token to use on every later call."""
    client_key = request.client.host if request.client else "unknown"
    return TokenResponse(access_token=accounts.login(db, form.username, form.password, client_key))
