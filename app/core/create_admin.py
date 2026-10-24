"""Create an administrator locally: ``python -m app.core.create_admin``."""
from getpass import getpass

from app.core import security
from app.db import repository
from app.db.session import get_sessionmaker, init_db


def main() -> None:
    init_db()
    username = input("New admin username: ").strip()
    password = getpass("New admin password (6–72 UTF-8 bytes): ")
    if len(username) < 3 or len(username) > 50:
        raise SystemExit("Username must be between 3 and 50 characters.")
    if len(password) < 6 or len(password.encode("utf-8")) > 72:
        raise SystemExit("Password must be 6–72 UTF-8 bytes long.")

    with get_sessionmaker()() as db:
        if repository.get_user_by_username(db, username):
            raise SystemExit("That username already exists. No account was changed.")
        user = repository.create_user(db, username, security.hash_password(password), role="admin")
        print(f"Admin account '{user.username}' created. Keep the password private.")


if __name__ == "__main__":
    main()
