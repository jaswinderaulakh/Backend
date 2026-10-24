"""Register inspectors, authenticate users, and resolve users from tokens."""
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import load_security_config
from app.core.errors import AuthError, ConflictError, RateLimitError
from app.db import repository
from app.db.models import User

# This process-local guard is deliberately simple for the single-process starter.
# The limits themselves live in config/security.yaml.
_failed_login_times: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_blocked_until: dict[tuple[str, str], float] = {}
_login_lock = Lock()


def register(db: Session, username: str, password: str) -> User:
    if repository.get_user_by_username(db, username):
        raise ConflictError("That username is already taken.")
    try:
        return repository.create_user(db, username, security.hash_password(password), role="inspector")
    except IntegrityError:
        db.rollback()
        raise ConflictError("That username is already taken.")


def login(db: Session, username: str, password: str, client_key: str = "") -> str:
    key = (username.strip().casefold(), client_key)
    config = load_security_config()["login_rate_limit"]
    now = monotonic()
    with _login_lock:
        until = _blocked_until.get(key, 0.0)
        if now < until:
            remaining = max(1, int(until - now + 0.999))
            raise RateLimitError(f"Too many sign-in attempts. Please wait {remaining} seconds and try again.")
        attempts = _failed_login_times[key]
        cutoff = now - float(config["window_seconds"])
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

    user = repository.get_user_by_username(db, username.strip())
    if user is None or not security.verify_password(password, user.password_hash):
        with _login_lock:
            attempts = _failed_login_times[key]
            attempts.append(monotonic())
            if len(attempts) >= int(config["attempts"]):
                _blocked_until[key] = monotonic() + float(config["lockout_seconds"])
        raise AuthError("Wrong username or password.")

    with _login_lock:
        _failed_login_times.pop(key, None)
        _blocked_until.pop(key, None)
    return security.create_access_token(user.id)


def user_from_token(db: Session, token: str) -> User:
    user_id = security.decode_access_token(token)
    user = repository.get_user(db, user_id) if user_id is not None else None
    if user is None:
        raise AuthError("Not logged in, or the login has expired.")
    return user
