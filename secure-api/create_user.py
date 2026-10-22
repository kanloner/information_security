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

# Length policy only. Composition rules ("one digit, one symbol") are
# deliberately not enforced: they encourage predictable substitutions such as
# Password1! while making the password harder to remember. Length is the
# property that actually raises the cost of a brute-force attack.
MIN_PASSWORD_LEN = 8


def create_user(username, password, path=None):
    """Insert a user, or replace the password of an existing one."""
    username = (username or "").strip()
    # Validate before touching the database so the caller gets a clear
    # ValueError instead of a sqlite constraint error.
    if not username:
        raise ValueError("username must not be empty")
    if len(username) > 64:
        raise ValueError("username must be at most 64 characters")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")

    db = init_db.connect(path)
    try:
        # One statement does both jobs:
        #   INSERT             - the account does not exist yet
        #   ON CONFLICT(...)   - it does, so only the hash is replaced
        # DO UPDATE SET ... = excluded.password_hash reads "take the value that
        # the INSERT wanted to store", which keeps the original id and
        # created_at intact. A DELETE + INSERT would change the row id and
        # orphan any future foreign key.
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
            (username, init_db.hash_password(password), init_db.utc_now().isoformat()),
        )
        db.commit()
    finally:
        # Guarantees the file handle is released even when the insert fails,
        # so the caller sees the real exception rather than a lock.
        db.close()
    return username


def main(argv=None):
    # argv is injectable so the function can be unit-tested without patching
    # sys.argv. argparse rejects unknown flags instead of ignoring them, which
    # catches typos such as --passsword (that would otherwise silently fall
    # back to the interactive prompt).
    parser = argparse.ArgumentParser(description="Create or reset an API account.")
    parser.add_argument("username", help="account name, 1-64 characters")
    parser.add_argument(
        "--password",
        help="password; if omitted, APP_USER_PASSWORD is used, then an interactive prompt",
    )
    parser.add_argument("--db", help="database path (default: $DB_PATH or app.db)")
    args = parser.parse_args(argv)

    # Three sources in decreasing order of exposure risk:
    #   1. --password    convenient, but visible in `ps` and in shell history
    #   2. APP_USER_PASSWORD  not in argv, for CI and provisioning scripts
    #   3. getpass       typed without echo, the safest interactive default
    password = args.password or os.environ.get("APP_USER_PASSWORD")
    if not password:
        password = getpass.getpass("password: ")

    try:
        username = create_user(args.username, password, args.db)
    # Both failure families are reported the same way: a policy violation is a
    # ValueError, a database problem is a sqlite3.Error. The message goes to
    # stderr (so it is not confused with data on stdout) and the exit code is
    # non-zero, which is what a script or CI step checks.
    except (ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"account ready: {username}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
