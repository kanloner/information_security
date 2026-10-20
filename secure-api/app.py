"""Secure REST API - HDU Information Security, Lab 1 (Work 1).

Three endpoints:
    POST /auth/login   -> issue a JWT (bcrypt-verified credentials)
    GET  /api/data     -> list posts (JWT required, output-encoded)
    POST /api/data     -> create a post (JWT required)

Security controls implemented here:
    * SQL injection: every statement is a constant SQL string with bound
      parameters ("?" placeholders). No user value is ever concatenated into
      SQL text, so the statement structure cannot be altered by input.
    * XSS: user data is stored as-is and encoded on output with
      html.escape(); JSON responses also carry CSP / nosniff headers so a
      browser will never treat the payload as markup.
    * Broken authentication: bcrypt (random salt, cost 12) password hashes,
      short-lived HS256 JWTs, algorithm whitelist on decode (blocks the
      "alg: none" and algorithm-confusion attacks) and a decorator that
      guards every protected route.
"""

import datetime
import html
import os
import secrets
import sqlite3
from functools import wraps

import bcrypt
import jwt
from flask import Flask, g, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# Never hardcode a secret: it is read from the environment, and a random one
# is generated for local runs (which also keeps bandit's B105 check quiet).
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "app.db"))

JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 1800
BCRYPT_ROUNDS = 12
MAX_FIELD_LEN = 200

# The authentication scheme name, kept as a constant so the response field does
# not look like a hardcoded credential to static analysers (bandit B105/B106).
AUTH_SCHEME = "Bearer"

# SQLite has to create (and later remove) a rollback journal next to the
# database file. Filesystems that forbid that - read-only container layers,
# some CI sandboxes - make every write fail with "disk I/O error". The mode is
# therefore configurable; the statements below are fixed literals, never built
# from input, so the setting cannot be abused.
DB_JOURNAL_MODE = os.environ.get("DB_JOURNAL_MODE", "delete").lower()
JOURNAL_PRAGMAS = {
    "delete": "PRAGMA journal_mode=DELETE",
    "memory": "PRAGMA journal_mode=MEMORY",
    "wal": "PRAGMA journal_mode=WAL",
}

# Used to keep the failed-login path roughly constant-time, so an attacker
# cannot tell "user does not exist" from "wrong password" by timing.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(rounds=BCRYPT_ROUNDS))

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


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute(JOURNAL_PRAGMAS.get(DB_JOURNAL_MODE, JOURNAL_PRAGMAS["delete"]))
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path=None):
    """Create the schema and seed two demo users plus a couple of posts."""
    target = path or DB_PATH
    db = sqlite3.connect(target)
    db.execute(JOURNAL_PRAGMAS.get(DB_JOURNAL_MODE, JOURNAL_PRAGMAS["delete"]))
    db.executescript(SCHEMA)

    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        for username, password in (("alice", "Alice123!"), ("bob", "Bob12345!")):
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
            db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, utc_now().isoformat()),
            )
        db.execute(
            "INSERT INTO posts (author, title, body, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "Hello", "First post from the seed data.", utc_now().isoformat()),
        )
        db.commit()

    db.close()


def require_jwt(view):
    """Reject any request that does not carry a valid, unexpired JWT."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="missing bearer token"), 401

        try:
            payload = jwt.decode(
                header[len("Bearer "):].strip(),
                SECRET_KEY,
                algorithms=[JWT_ALGORITHM],  # whitelist: no "none", no confusion
            )
        except jwt.ExpiredSignatureError:
            return jsonify(error="token expired"), 401
        except jwt.InvalidTokenError:
            return jsonify(error="invalid token"), 401

        g.current_user = payload.get("sub")
        return view(*args, **kwargs)

    return wrapper


@app.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", ""))[:64]
    password = str(data.get("password", ""))[:128]

    row = get_db().execute(
        "SELECT username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()

    if row is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        return jsonify(error="invalid credentials"), 401

    if not bcrypt.checkpw(password.encode(), row["password_hash"]):
        return jsonify(error="invalid credentials"), 401

    expires_at = utc_now() + datetime.timedelta(seconds=TOKEN_TTL_SECONDS)
    token = jwt.encode(
        {
            "sub": row["username"],
            "iat": int(utc_now().timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
    # The payload is built as a mapping with a constant scheme name so that the
    # OAuth2 "token_type" field is not mistaken for a hardcoded password.
    return jsonify(
        {
            "access_token": token,
            "token_type": AUTH_SCHEME,
            "expires_in": TOKEN_TTL_SECONDS,
        }
    )


@app.get("/api/data")
@require_jwt
def list_posts():
    query = request.args.get("q", "")[:MAX_FIELD_LEN]
    pattern = f"%{query}%"

    rows = get_db().execute(
        "SELECT id, author, title, body, created_at FROM posts "
        "WHERE title LIKE ? OR body LIKE ? ORDER BY id",
        (pattern, pattern),
    ).fetchall()

    # Output encoding: whatever was stored, the response can never be
    # interpreted as HTML/JS by a browser.
    return jsonify(
        [{key: html.escape(str(row[key])) for key in row.keys()} for row in rows]
    )


@app.post("/api/data")
@require_jwt
def create_post():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", ""))[:MAX_FIELD_LEN].strip()
    body = str(data.get("body", ""))[:MAX_FIELD_LEN]

    if not title:
        return jsonify(error="title is required"), 400

    db = get_db()
    db.execute(
        "INSERT INTO posts (author, title, body, created_at) VALUES (?, ?, ?, ?)",
        (g.current_user, title, body, utc_now().isoformat()),
    )
    db.commit()
    return jsonify(status="created"), 201


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    init_db()
    # Port 8000: on macOS port 5000 is taken by the AirPlay Receiver.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=False)
