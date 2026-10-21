"""Create or reset a single account.

This is the user-management path that a real deployment needs, and it is also
how the tests build their fixtures: nothing in the application can create a
user, so account creation cannot be reached from the network at all.

    python create_user.py alice --password 'Alice123!'
    APP_USER_PASSWORD=... python create_user.py bob
    python create_user.py carol --db /tmp/other.db

The password is hashed with bcrypt before it touches the database; the plain
value is never written to disk or to a log line.
"""

import argparse
import getpass
import os
import sqlite3
import sys

import init_db

MIN_PASSWORD_LEN = 8


def create_user(username, password, path=None):
    """Insert a user, or replace the password of an existing one."""
    username = (username or "").strip()
    if not username:
        raise ValueError("username must not be empty")
    if len(username) > 64:
        raise ValueError("username must be at most 64 characters")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")

    db = init_db.connect(path)
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
            (username, init_db.hash_password(password), init_db.utc_now().isoformat()),
        )
        db.commit()
    finally:
        db.close()
    return username


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create or reset an API account.")
    parser.add_argument("username", help="account name, 1-64 characters")
    parser.add_argument(
        "--password",
        help="password; if omitted, APP_USER_PASSWORD is used, then an interactive prompt",
    )
    parser.add_argument("--db", help="database path (default: $DB_PATH or app.db)")
    args = parser.parse_args(argv)

    password = args.password or os.environ.get("APP_USER_PASSWORD")
    if not password:
        password = getpass.getpass("password: ")

    try:
        username = create_user(args.username, password, args.db)
    except (ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"account ready: {username}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
