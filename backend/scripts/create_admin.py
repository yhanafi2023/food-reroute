"""Create an admin account (with DEMO_MODE off there is no seeded admin).

  cd backend
  DATABASE_URL=postgresql://... python -m scripts.create_admin admin@yourorg.org "Your Name"

The password is asked for twice at the prompt (or read from ADMIN_PASSWORD, for automation),
so it never lands in shell history.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


def create_admin(email: str, name: str, password: str) -> User:
    email = email.strip().lower()
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise SystemExit(f"The password must be {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters.")
    with SessionLocal() as db:
        if db.query(User).filter_by(email=email).first():
            raise SystemExit(f"An account with {email} already exists.")
        user = User(email=email, password_hash=hash_password(password), name=name.strip(),
                    first_name=name.split()[0], role="admin")
        db.add(user)
        db.commit()
        return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a FoodFlow admin account.")
    parser.add_argument("email")
    parser.add_argument("name")
    args = parser.parse_args()
    password = os.environ.get("ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise SystemExit("The passwords do not match.")
    user = create_admin(args.email, args.name, password)
    print(f"Admin {user.email} created (id {user.id}).")


if __name__ == "__main__":
    main()
