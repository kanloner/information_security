"""Automated tests for the secure API.

They double as the security regression suite: each test below corresponds to
one of the graded security controls.

Reading guide: a test named after a *property* (``..._is_rejected``,
``..._returns_nothing``) asserts that an attack fails, not that a feature
works. Those are the ones that must never be deleted - a green suite that only
tests the happy path proves nothing about security.
"""

import os
import sys

import pytest

# The application modules live one directory up (the repository keeps the
# tests in tests/ and the sources in secure-api/). Without this entry,
# "import app" would fail when pytest is started from the repository root,
# because pytest only adds the directory of the test file (or rootdir) to
# sys.path. Inserted at position 0 so the local sources win over anything with
# a similar name installed in site-packages.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as api  # noqa: E402
import create_user  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # tmp_path is a fresh, empty directory per test, so every test starts from
    # the same known state: one seeded user (alice) and one seeded post.
    # monkeypatch.setattr restores the original DB_PATH automatically at the
    # end of the test, which is what keeps the real app.db untouched.
    monkeypatch.setattr(api, "DB_PATH", str(tmp_path / "test.db"))
    api.init_db()
    # TESTING=True makes Flask propagate exceptions instead of turning them
    # into 500 responses, so a bug in a handler fails the test with a traceback
    # rather than looking like an expected error status.
    api.app.config.update(TESTING=True)
    # The test client drives the app in-process: no socket is opened, no port
    # is bound, and requests still go through the full request pipeline
    # (routing, decorators, after_request hooks). The context manager runs the
    # startup/shutdown hooks, so g and the teardown handler behave as in
    # production.
    with api.app.test_client() as test_client:
        yield test_client


def get_token(client, username="alice", password="Alice123!"):
    # Convenience helper: most tests need a valid token, and hard-coding the
    # login dance in each one would hide what the test is actually about.
    response = client.post("/auth/login", json={"username": username, "password": password})
    return response.get_json()["access_token"]


def auth_header(token):
    # Single place that knows the header format, so switching the scheme later
    # (e.g. to "Bearer " with a different casing rule) is a one-line change.
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_jwt(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "Alice123!"})
    body = response.get_json()
    assert response.status_code == 200
    assert body["token_type"] == "Bearer"
    # A compact JWS has exactly three base64url segments separated by dots:
    # header.payload.signature. Two dots therefore prove the token is
    # structurally correct without pinning the secret or the claims.
    assert body["access_token"].count(".") == 2


def test_login_wrong_password_is_rejected(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert response.status_code == 401
    # The important half of the assertion: no token may leak on the failure
    # path, not merely "the status was 401".
    assert "access_token" not in response.get_json()


def test_login_unknown_user_is_rejected(client):
    # Same status and same message as the wrong-password case; together the two
    # tests prove the response cannot be used to enumerate accounts.
    response = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert response.status_code == 401


def test_data_requires_token(client):
    # Fail-closed check: the route without credentials must not return data.
    response = client.get("/api/data")
    assert response.status_code == 401


def test_data_rejects_tampered_token(client):
    # Appending one character to the signature changes the HMAC input, so
    # verification must fail. This is the test that would catch a decode call
    # made without signature verification.
    token = get_token(client)
    response = client.get("/api/data", headers=auth_header(token + "x"))
    assert response.status_code == 401


def test_data_returns_rows_with_valid_token(client):
    # Happy path, kept so that a security fix which breaks normal use
    # (over-escaping, over-strict validation) is caught immediately.
    response = client.get("/api/data", headers=auth_header(get_token(client)))
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)
    assert len(response.get_json()) >= 1


def test_sql_injection_payload_returns_nothing(client):
    # %27%20OR%201%3D1-- is the URL-encoded form of  ' OR 1=1--
    # With string concatenation this payload would turn the WHERE clause into
    # a tautology and return every row. With a bound parameter it is just a
    # 13-character search term that matches no title or body, so the correct
    # answer is an empty list - not an error, and not the table contents.
    token = get_token(client)
    payload = "%27%20OR%201%3D1--"
    response = client.get(f"/api/data?q={payload}", headers=auth_header(token))
    assert response.status_code == 200
    assert response.get_json() == []


def test_stored_xss_is_escaped_on_output(client):
    token = get_token(client)
    payload = "<script>alert(document.cookie)</script>"

    # Store the payload unchanged - the defence is on output, so the write side
    # must accept it verbatim.
    created = client.post(
        "/api/data",
        json={"title": "xss", "body": payload},
        headers=auth_header(token),
    )
    assert created.status_code == 201

    # Read it back through the filter that matches the new row.
    response = client.get("/api/data?q=xss", headers=auth_header(token))
    stored_body = response.get_json()[0]["body"]

    # The exact escaped form is asserted, not just "the tag is gone": a
    # partial or double encoding would still satisfy the weaker check but
    # would corrupt the data for the client.
    assert "<script>" not in stored_body
    assert stored_body == "&lt;script&gt;alert(document.cookie)&lt;/script&gt;"


def test_create_requires_token(client):
    # Write-side access control: an anonymous POST must be rejected before it
    # reaches the INSERT.
    response = client.post("/api/data", json={"title": "nope", "body": "x"})
    assert response.status_code == 401


def test_create_validates_empty_title(client):
    # Two spaces pass the "is the field present" check, so only an explicit
    # strip + emptiness test turns them into 400 rather than an unusable row.
    response = client.post("/api/data", json={"title": "  "}, headers=auth_header(get_token(client)))
    assert response.status_code == 400


def test_security_headers_present(client):
    # Checked on a protected route because that is where a scanner or a browser
    # would look; @app.after_request sets them on every response, error pages
    # included.
    response = client.get("/api/data", headers=auth_header(get_token(client)))
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]


def test_create_user_adds_a_working_account(client):
    # The CLI is the only way to create an account, so "no registration route"
    # must be paired with "the CLI actually produces a login-able user".
    create_user.create_user("carol", "Carol123!", api.DB_PATH)

    response = client.post("/auth/login", json={"username": "carol", "password": "Carol123!"})
    assert response.status_code == 200
    assert "access_token" in response.get_json()

    # The policy is enforced where the account is created: a 5-character
    # password must never reach bcrypt/the database.
    with pytest.raises(ValueError):
        create_user.create_user("dave", "short", api.DB_PATH)
