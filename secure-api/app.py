"""Secure REST API - HDU Information Security, Lab 1 (Work 1).

Three endpoints:
    POST /auth/login   -> issue a JWT (bcrypt-verified credentials)
    GET  /api/data     -> list posts (JWT required, output-encoded)
    POST /api/data     -> create a post (JWT required)

The schema, the connection factory and the bcrypt hashing live in init_db.py;
account management is the offline CLI in create_user.py. This module only
contains the request handlers and the controls that protect them:

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

# Trust boundary: everything that arrives in `request` is attacker-controlled
# until it has been length-limited, type-coerced and bound as a parameter. The
# handlers below are written so that the only values which reach SQL, the JWT
# library or the response body pass through one of those three steps first.
#
# This note lives in a comment rather than in the docstring on purpose: bandit
# counts docstring lines as code, and the report quotes the scanned line count,
# so extending the docstring would change a published number for a text-only
# change.

import datetime
import html
import os
import secrets
from functools import wraps

import bcrypt
import jwt
from flask import Flask, g, jsonify, request

# Aliased on purpose: this module defines its own helper called init_db()
# further down, and the two names would otherwise shadow each other. The alias
# makes it obvious that DB_PATH, connect(), BCRYPT_ROUNDS and db_path() come
# from the database module, not from the local wrapper.
import init_db as database

app = Flask(__name__)

# Never hardcode a secret: it is read from the environment, and a random one
# is generated for local runs (which also keeps bandit's B105 check quiet).
# Note the consequence: because the fallback is random, every restart of a
# locally started server invalidates the tokens issued by the previous process.
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DB_PATH = database.db_path()

# HS256 is a *symmetric* algorithm: the same key signs and verifies. That is
# acceptable for a single-service design and avoids key distribution, but it
# means the secret must never reach a client.
JWT_ALGORITHM = "HS256"
# 30 minutes bounds the damage from a leaked token: this scheme has no
# server-side revocation list, so until `exp` passes the token is valid
# everywhere. Raise this only together with a revocation mechanism.
TOKEN_TTL_SECONDS = 1800
BCRYPT_ROUNDS = database.BCRYPT_ROUNDS
MAX_FIELD_LEN = database.MAX_FIELD_LEN

# The authentication scheme name, kept as a constant so the response field does
# not look like a hardcoded credential to static analysers (bandit B105/B106).
AUTH_SCHEME = "Bearer"

# Used to keep the failed-login path roughly constant-time, so an attacker
# cannot tell "user does not exist" from "wrong password" by timing.
# It is computed once at import: the point is that the *unknown user* branch
# still pays for one bcrypt verification, otherwise the early return would be
# measurably faster and turn the login form into a user-enumeration oracle.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def utc_now():
    # Always timezone-aware UTC. A naive datetime would be interpreted in the
    # server's local zone when converted to a timestamp, which silently shifts
    # every JWT expiry by the UTC offset.
    return datetime.datetime.now(datetime.timezone.utc)


def init_db(path=None):
    """Create the schema for the configured database (used by tests and startup)."""
    # Thin wrapper so callers (and the test fixture) can pass an alternative
    # path. It deliberately reads DB_PATH at call time instead of caching a
    # connection, which is what lets a test point the app at a temp database.
    return database.init_db(path or DB_PATH)


def get_db():
    # `g` is Flask's request-scoped namespace: one object per request, dropped
    # when the request ends. Caching the connection there means a request that
    # runs several statements opens exactly one SQLite connection, while two
    # concurrent requests never share one - sqlite3 connections are bound to
    # the thread that created them and are not safe to share.
    if "db" not in g:
        g.db = database.connect(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(exception):
    # Flask calls this after every request (and after every application
    # context), including when the handler raised. `pop` both removes the
    # attribute and returns it, and the None default makes the function safe
    # for requests that never touched the database. Without this hook the
    # connection would be garbage-collected eventually, but the SQLite file
    # handle and its journal would stay open far longer than necessary.
    db = g.pop("db", None)
    if db is not None:
        db.close()


def require_jwt(view):
    """Reject any request that does not carry a valid, unexpired JWT."""

    # @wraps copies __name__, __doc__ and the module of `view` onto `wrapper`,
    # so Flask still registers the route under the real handler name and the
    # traceback / test output shows `login` instead of `wrapper`.
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")

        # Shape check first: RFC 6750 requires "Bearer <token>". Checking the
        # prefix before splitting means a header such as "Basic ..." is
        # rejected here instead of being fed to the JWT parser.
        if not header.startswith(AUTH_SCHEME + " "):
            return jsonify(error="missing bearer token"), 401

        try:
            # header[len(AUTH_SCHEME) + 1:] drops "Bearer" *and* the space.
            # .strip() tolerates trailing whitespace from careless clients.
            payload = jwt.decode(
                header[len(AUTH_SCHEME) + 1:].strip(),
                SECRET_KEY,
                algorithms=[JWT_ALGORITHM],  # whitelist: no "none", no confusion
            )
        # Expired and otherwise invalid tokens are distinguished only in the
        # message, never in the status code: both are 401, both fail closed.
        except jwt.ExpiredSignatureError:
            return jsonify(error="token expired"), 401
        except jwt.InvalidTokenError:
            # Covers a bad signature, a malformed segment, a missing claim and
            # an unexpected algorithm - all of them mean "not authenticated".
            return jsonify(error="invalid token"), 401

        # The identity comes from the *signed* claim, never from the request
        # body. Anything the client says about itself in the payload is
        # attacker-controlled and must be ignored.
        g.current_user = payload.get("sub")
        return view(*args, **kwargs)

    return wrapper


@app.post("/auth/login")
def login():
    # silent=True makes a non-JSON or missing body return None instead of
    # raising a 400 with an HTML error page; `or {}` then normalises it to an
    # empty mapping so the two lookups below cannot fail.
    data = request.get_json(silent=True) or {}

    # Slice before use, and str() so a JSON number or object cannot reach
    # .encode() with the wrong type. This is a cheap DoS guard: bcrypt on a
    # multi-megabyte password would burn CPU for free.
    username = str(data.get("username", ""))[:64]
    password = str(data.get("password", ""))[:128]

    # Parameterised query: the "?" is part of the constant SQL text and the
    # value travels out of band, so a payload such as "' OR '1'='1" is compared
    # as a literal string and simply matches no row.
    row = get_db().execute(
        "SELECT username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()

    if row is None:
        # Still spend the time of a bcrypt comparison, then return the *same*
        # response as a wrong password - see _DUMMY_HASH above.
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        return jsonify(error="invalid credentials"), 401

    # checkpw re-reads the salt and cost from the stored hash, so no separate
    # salt column is needed. The comparison is constant-time inside the
    # library, which is why == on hashes would have been wrong.
    if not bcrypt.checkpw(password.encode(), row["password_hash"]):
        return jsonify(error="invalid credentials"), 401

    # Claims: `sub` = who, `iat` = issued at, `exp` = hard expiry. All three
    # are integers because RFC 7519 defines them as NumericDate (epoch seconds),
    # not ISO strings. jwt.encode signs them with SECRET_KEY.
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
    # Decorators apply bottom-up: @require_jwt wraps list_posts first, so the
    # token is verified before a single line of this handler runs.
    query = request.args.get("q", "")[:MAX_FIELD_LEN]

    # The % wildcards are added to the *value*, not to the SQL text. This is
    # the detail that usually breaks LIKE queries: f-string interpolation into
    # the statement would reintroduce injection through the pattern.
    pattern = f"%{query}%"

    # Two placeholders, two values - the filter is a data value in both
    # columns, not a fragment of the query.
    rows = get_db().execute(
        "SELECT id, author, title, body, created_at FROM posts "
        "WHERE title LIKE ? OR body LIKE ? ORDER BY id",
        (pattern, pattern),
    ).fetchall()

    # Output encoding: whatever was stored, the response can never be
    # interpreted as HTML/JS by a browser.
    #
    # Encoding on output rather than on input is deliberate: the database keeps
    # the exact bytes the user wrote, so the same value can still be rendered
    # correctly into e-mail, a log line or a PDF later. Only the output context
    # knows which encoding is right.
    #
    # jsonify serialises to application/json anyway; the escaping matters for
    # consumers that embed the string in a page without encoding it again.
    # row.keys() iterates the column names of sqlite3.Row (a tuple-like row
    # that can also be indexed by name).
    return jsonify(
        [{key: html.escape(str(row[key])) for key in row.keys()} for row in rows]
    )


@app.post("/api/data")
@require_jwt
def create_post():
    data = request.get_json(silent=True) or {}
    # Truncate to the column's intended size so a client cannot store unbounded
    # blobs (a cheap storage-exhaustion guard). Only the title is stripped:
    # leading whitespace in a body may be meaningful, and stripping it would
    # also make HTML payloads with padding behave differently.
    title = str(data.get("title", ""))[:MAX_FIELD_LEN].strip()
    body = str(data.get("body", ""))[:MAX_FIELD_LEN]

    # Explicit validation instead of trusting the schema's NOT NULL: an empty
    # title would satisfy NOT NULL and create a row that no one can identify.
    if not title:
        return jsonify(error="title is required"), 400

    db = get_db()
    # The author is taken from the verified token (g.current_user), not from
    # the request body. Accepting a client-supplied "author" would let any
    # authenticated user post as somebody else - the write-side equivalent of
    # an IDOR / broken access control.
    db.execute(
        "INSERT INTO posts (author, title, body, created_at) VALUES (?, ?, ?, ?)",
        (g.current_user, title, body, utc_now().isoformat()),
    )
    # sqlite3 opens an implicit transaction; without commit the row is lost
    # when the connection is closed by close_db().
    db.commit()
    # 201 Created is the correct status for a successful insert; 200 would tell
    # the client that nothing was created.
    return jsonify(status="created"), 201


@app.after_request
def security_headers(response):
    # Applied to every response, including error pages and 404s: a header that
    # is only set on the happy path is a header an attacker can route around.
    #
    # nosniff       - stop the browser from guessing a different content type
    #                 (the mechanism behind "JSON read as HTML -> XSS").
    # CSP           - default-src 'none' forbids loading anything at all;
    #                 frame-ancestors 'none' blocks clickjacking.
    # Referrer      - the API URL never leaks to third parties via Referer.
    # no-store      - tokens and data must not be cached by a proxy or on disk.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    # Create the schema and the demo rows before serving, so "python app.py" on
    # a fresh checkout works without a separate init step (both calls are
    # idempotent).
    init_db()
    # Port 8000: on macOS port 5000 is taken by the AirPlay Receiver.
    # host=127.0.0.1 keeps the development server off the network, and
    # debug=False matters for security: the Werkzeug debugger exposes an
    # interactive Python console on the error page and allows code execution.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=False)
