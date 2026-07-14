"""One-off: seed / rotate the admin users. Prints the plaintext passwords.

Usage:
    heroku run python seed_users.py                            -a hi-engineer-app
    heroku run python seed_users.py --rotate                   -a hi-engineer-app
    heroku run python seed_users.py --rotate somebody@x.com    -a hi-engineer-app

Defaults to the two hardcoded admin emails when no email args are given.
"""

from __future__ import annotations

import argparse
import secrets
import sys

import db
from auth import hash_password

DEFAULT_EMAILS = [
    "sebastiaan.corstjens@blueprojects.com",
    "pogancristian@gmail.com",
]


def generate_password() -> str:
    # 16 random bytes → 22 URL-safe base64 chars, ~128 bits of entropy
    return secrets.token_urlsafe(16)


def seed(emails: list[str], rotate: bool) -> int:
    if not db.using_db():
        print("ERROR: DATABASE_URL not set; cannot seed users."); return 2
    db.init_db()  # make sure the users table exists

    printed = 0
    for email in emails:
        email = email.strip().lower()
        existing = db.get_user(email)
        if existing and not rotate:
            created = (existing.get("created_at") or "")[:10]
            print(f"{email:45s}  EXISTS (created {created})  — pass --rotate to regenerate")
            continue
        password = generate_password()
        db.upsert_user(email, hash_password(password), is_admin=True)
        action = "ROTATED" if existing else "CREATED"
        print(f"{email:45s}  {action}  password: {password}")
        printed += 1

    print(f"\n{printed} password(s) printed. Copy them now — this is the only display.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rotate", action="store_true",
                   help="regenerate password even for existing users")
    p.add_argument("emails", nargs="*", help=f"defaults to {DEFAULT_EMAILS}")
    args = p.parse_args()
    return seed(args.emails or DEFAULT_EMAILS, rotate=args.rotate)


if __name__ == "__main__":
    sys.exit(main())
