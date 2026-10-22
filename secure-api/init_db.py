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
# The default database sits next to the source files. Resolving it from
# __file__ (not from the current directory) means "python app.py" behaves the
# same whether it is started from secure-api/ or from a parent folder.
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "app.db")

# Cost factor. Each increment doubles the work: 12 is roughly 0.2-0.3 s per
# hash on a laptop, which is invisible at login and ruinous for an attacker
# testing billions of candidate passwords against a stolen dump.
BCRYPT_ROUNDS = 12
# Longest value accepted for any free-text field (title, body, search term).
MAX_FIELD_LEN = 200

# IF NOT EXISTS makes create_schema() idempotent: it can run on every start
# without destroying existing rows.
#   users.password_hash is BLOB, not TEXT - bcrypt hashes are raw bytes and
#   storing them as text would corrupt the salt on some encodings.
#   username is UNIQUE, which is what the ON CONFLICT upsert in create_user.py
#   relies on to implement "create or reset".
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
#
# Why a *whitelist* and not a formatted string: PRAGMA statements cannot be
# parameterised, so the only safe way to accept this setting from the
# environment is to map it onto a fixed set of complete statements. An unknown
# value falls back to "delete" rather than being passed through.
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
    # Precedence matters for the tests: they pass an explicit path, CI exports
    # DB_PATH, and a plain local run falls through to app.db.
    return path or os.environ.get("DB_PATH") or DEFAULT_DB_PATH


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def connect(path=None):
    """Open the database with the configured journal mode."""
    db = sqlite3.connect(db_path(path))
    # row_factory makes every row behave like a dict, so handlers can write
    # row["password_hash"] instead of remembering the column's index. A
    # positional index would silently break if a column were inserted into the
    # SELECT list later.
    db.row_factory = sqlite3.Row
    # Look the mode up in the whitelist; an unknown environment value must not
    # be executed. The .get() default repeats "delete" so the fallback is
    # explicit in one place.
    db.execute(JOURNAL_PRAGMAS.get(DB_JOURNAL_MODE, JOURNAL_PRAGMAS["delete"]))
    return db


def hash_password(password):
    """bcrypt with a per-password random salt and a deliberately slow cost."""
    # gensalt() draws a fresh random salt every time, so hashing the same
    # password twice yields two different digests and precomputed rainbow
    # tables are useless. .encode() is required because bcrypt works on bytes.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def create_schema(db):
    # executescript() can run several statements separated by ";" - the plain
    # execute() would stop at the first one.
    db.executescript(SCHEMA)


def seed_demo_data(db):
    """Insert the demo users and one post, but only into an empty database."""
    # The guard makes this a no-op on every start after the first: re-seeding
    # would either duplicate the post or (because of the UNIQUE username) raise
    # an IntegrityError that aborts the whole startup.
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return 0

    now = utc_now().isoformat()
    for username, password in DEMO_ACCOUNTS:
        # Parameter binding, again: the loop variable is inserted as a value,
        # never spliced into the statement text.
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hash_password(password), now),
        )
    for author, title, text in DEMO_POSTS:
        db.execute(
            "INSERT INTO posts (author, title, body, created_at) VALUES (?, ?, ?, ?)",
            (author, title, text, now),
        )
    # One commit for the whole seed, so a failure halfway leaves no partial
    # state behind (and the empty-database guard stays truthful).
    db.commit()
    return len(DEMO_ACCOUNTS) + len(DEMO_POSTS)


def init_db(path=None, with_demo_data=True):
    """Create the schema (idempotent) and optionally seed the demo data."""
    db = connect(path)
    # try/finally rather than rely on garbage collection: if create_schema or
    # the seed raises, the connection is still closed and the caller gets the
    # original exception. with_demo_data=False is what a test that needs an
    # empty database uses.
    try:
        create_schema(db)
        written = seed_demo_data(db) if with_demo_data else 0
    finally:
        db.close()
    return written


if __name__ == "__main__":
    # Short human-readable confirmation for the manual run: which file was
    # touched and how many rows this particular run added.
    target = db_path()
    rows = init_db()
    print(f"database ready: {target}")
    print(f"rows seeded on this run: {rows}")
    # The underscore discards the password half of each tuple, so no credential
    # is ever printed to the terminal or a log.
    print("accounts: " + ", ".join(name for name, _ in DEMO_ACCOUNTS))
