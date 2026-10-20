# secure-api — Flask implementation for Laboratory Work No. 1

The full write-up (API reference, security measures, CI/CD, CVE-2021-25646 analysis,
root cause, fix and proof of elimination) is in the **[repository README](../README.md)**.

This folder contains the runnable project:

```
app.py                      three endpoints + JWT middleware (single file, ~240 lines)
requirements.txt            pinned dependencies (Flask, PyJWT, bcrypt)
demo.sh                     end-to-end demonstration used for the report evidence
tests/test_api.py           11 functional + security tests
cve/CVE-2021-25646/         vulnerable environment (Apache Druid 0.20.0) + reproduce.sh + verify_fix.sh
fixes/                      patched environment (Druid 0.20.1): Dockerfile + compose + README
```

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:8000
./demo.sh                     # in another terminal
```

Demo accounts: `alice / Alice123!`, `bob / Bob12345!`.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | no | returns a JWT (HS256, 30 min) |
| GET | `/api/data?q=` | Bearer | list posts, substring filter |
| POST | `/api/data` | Bearer | create a post |

## Security controls

* **SQLi** — constant SQL strings, every value bound as a parameter (`?`), including the
  `LIKE` pattern.
* **XSS** — data stored as-is, `html.escape()` on output, plus `nosniff` and CSP headers.
* **Authentication** — bcrypt (cost 12, per-user salt), JWT with an algorithm whitelist on
  decode, decorator on every protected route, no secret in the repository.

## Scanners

```bash
pytest -q
bandit -r ./app.py
pip-audit -r requirements.txt
```

The same commands run in CI on every push and pull request
(`.github/workflows/ci.yml` at the repository root).
