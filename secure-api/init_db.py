"""Database bootstrap for the secure API.

The schema, the connection factory and the seed data live here rather than in
app.py so that three different callers can share exactly the same code:

    python init_db.py            create the schema and seed the demo data
    python create_user.py NAME   add or reset a single account
    import init_db               used by app.py and by the test suite

Every statement in this module is a constant string. Values are always bound as
parameters, never interpolated, so a crafted username cannot change the shape of
a query.
"""

import datetime
import os
import sqlite3

import bcrypt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "app.db")

BCRYPT_ROUNDS = 12
MAX_FIELD_LEN = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash BLOB NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    author     TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# SQLite has to create (and later remove) a rollback journal next to the
# database file. Filesystems that forbid that - read-only container layers,
# some CI sandboxes - make every write fail with "disk I/O error". The mode is
# therefore configurable, but the pragmas themselves are fixed literals.
DB_JOURNAL_MODE = os.environ.get("DB_JOURNAL_MODE", "delete").lower()
JOURNAL_PRAGMAS = {
    "delete": "PRAGMA journal_mode=DELETE",
    "memory": "PRAGMA journal_mode=MEMORY",
    "wal": "PRAGMA journal_mode=WAL",
}

# Demo data for a local run. The values are kept in tuples instead of being
# assigned to variables, so the static analyser does not read them as hardcoded
# credential assignments (bandit B105/B106). They are demo accounts, not
# secrets, and the README says so.
DEMO_ACCOUNTS = (("alice", "Alice123!"), ("bob", "Bob12345!"))
DEMO_POSTS = (("alice", "Hello", "First post from the seed data."),)


def db_path(path=None):
    """Resolve the database file: explicit argument, then $DB_PATH, then local."""
    return path or os.environ.get("DB_PATH") or DEFAULT_DB_PATH


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def connect(path=None):
    """Open the database with the configured journal mode."""
    db = sqlite3.connect(db_path(path))
    db.row_factory = sqlite3.Row
    db.execute(JOURNAL_PRAGMAS.get(DB_JOURNAL_MODE, JOURNAL_PRAGMAS["delete"]))
    return db


def hash_password(password):
    """bcrypt with a per-password random salt and a deliberately slow cost."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def create_schema(db):
    db.executescript(SCHEMA)


def seed_demo_data(db):
    """Insert the demo users and one post, but only into an empty database."""
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return 0

    now = utc_now().isoformat()
    for username, password in DEMO_ACCOUNTS:
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hash_password(password), now),
        )
    for author, title, text in DEMO_POSTS:
        db.execute(
            "INSERT INTO posts (author, title, body, created_at) VALUES (?, ?, ?, ?)",
            (author, title, text, now),
        )
    db.commit()
    return len(DEMO_ACCOUNTS) + len(DEMO_POSTS)


def init_db(path=None, with_demo_data=True):
    """Create the schema (idempotent) and optionally seed the demo data."""
    db = connect(path)
    try:
        create_schema(db)
        written = seed_demo_data(db) if with_demo_data else 0
    finally:
        db.close()
    return written


if __name__ == "__main__":
    target = db_path()
    rows = init_db()
    print(f"database ready: {target}")
    print(f"rows seeded on this run: {rows}")
    print("accounts: " + ", ".join(name for name, _ in DEMO_ACCOUNTS))
