"""Automated tests for the secure API.

They double as the security regression suite: each test below corresponds to
one of the graded security controls.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as api  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", str(tmp_path / "test.db"))
    api.init_db()
    api.app.config.update(TESTING=True)
    with api.app.test_client() as test_client:
        yield test_client


def get_token(client, username="alice", password="Alice123!"):
    response = client.post("/auth/login", json={"username": username, "password": password})
    return response.get_json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_jwt(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "Alice123!"})
    body = response.get_json()
    assert response.status_code == 200
    assert body["token_type"] == "Bearer"
    assert body["access_token"].count(".") == 2


def test_login_wrong_password_is_rejected(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert response.status_code == 401
    assert "access_token" not in response.get_json()


def test_login_unknown_user_is_rejected(client):
    response = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert response.status_code == 401


def test_data_requires_token(client):
    response = client.get("/api/data")
    assert response.status_code == 401


def test_data_rejects_tampered_token(client):
    token = get_token(client)
    response = client.get("/api/data", headers=auth_header(token + "x"))
    assert response.status_code == 401


def test_data_returns_rows_with_valid_token(client):
    response = client.get("/api/data", headers=auth_header(get_token(client)))
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)
    assert len(response.get_json()) >= 1


def test_sql_injection_payload_returns_nothing(client):
    token = get_token(client)
    payload = "%27%20OR%201%3D1--"
    response = client.get(f"/api/data?q={payload}", headers=auth_header(token))
    assert response.status_code == 200
    assert response.get_json() == []


def test_stored_xss_is_escaped_on_output(client):
    token = get_token(client)
    payload = "<script>alert(document.cookie)</script>"

    created = client.post(
        "/api/data",
        json={"title": "xss", "body": payload},
        headers=auth_header(token),
    )
    assert created.status_code == 201

    response = client.get("/api/data?q=xss", headers=auth_header(token))
    stored_body = response.get_json()[0]["body"]

    assert "<script>" not in stored_body
    assert stored_body == "&lt;script&gt;alert(document.cookie)&lt;/script&gt;"


def test_create_requires_token(client):
    response = client.post("/api/data", json={"title": "nope", "body": "x"})
    assert response.status_code == 401


def test_create_validates_empty_title(client):
    response = client.post("/api/data", json={"title": "  "}, headers=auth_header(get_token(client)))
    assert response.status_code == 400


def test_security_headers_present(client):
    response = client.get("/api/data", headers=auth_header(get_token(client)))
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
