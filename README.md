# Information Security — Laboratory Work No. 1

**Secure REST API development with CI/CD security scanning and real CVE vulnerability analysis**

| Field | Value |
|---|---|
| Student | Zhaohan Liao |
| HDU number | 23320330 |
| Variant | CVE-2021-25646 |
| Stack | Python 3.11+, Flask 3, SQLite, PyJWT, bcrypt |
| SAST / SCA | bandit / pip-audit, run by GitHub Actions on every push and PR |
| Vulnerability analysed | CVE-2021-25646 — Apache Druid embedded JavaScript RCE (<= 0.20.0) |
| Report | [`report/Lab1_Report_Work1.docx`](report/Lab1_Report_Work1.docx) |

The work covers the full security lifecycle: building an API that resists the most
common OWASP Top 10 attack classes, automating the detection of defects in CI/CD,
and then taking a real CVE from the public databases to a reproducible experiment —
launching the vulnerable version, exploiting it, explaining the root cause, patching
it and proving that the same attack no longer works.

```
.
├── README.md                        # this file - project, security, CI/CD and CVE write-up
├── .github/workflows/ci.yml         # SAST + SCA + tests on every push / pull request
├── secure-api/
│   ├── app.py                       # HTTP handlers, JWT middleware, response headers
│   ├── init_db.py                   # schema, connection factory, demo seed data
│   ├── create_user.py               # offline account CLI (bcrypt, no HTTP route)
│   ├── requirements.txt             # pinned runtime dependencies
│   ├── demo.sh                      # end-to-end demo used for the evidence below
│   ├── tests/test_api.py            # 12 functional + security tests
│   ├── cve/CVE-2021-25646/          # vulnerable environment (Druid 0.20.0), reproduce.sh, verify_fix.sh
│   └── fixes/                       # patched environment (Druid 0.20.1) - the "folder with fixes"
├── docs/screenshots/                # evidence used in the report
└── report/Lab1_Report_Work1.docx
```

> The workflow lives at the repository root because GitHub Actions only reads
> `.github/workflows/` there; every step runs with `working-directory: secure-api`.

---

## 1. Quick start

```bash
cd secure-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python init_db.py                 # create the schema and the demo data
python app.py                     # serves http://127.0.0.1:8000
```

`python init_db.py` is optional — the server calls the same function on startup.
To add an account without restarting anything:

```bash
python create_user.py carol --password 'Carol123!'   # or APP_USER_PASSWORD=... / interactive prompt
```

Accounts are only created through that CLI, never over HTTP, so there is no
registration endpoint to attack. Demo accounts created on the first run are
`alice / Alice123!` and `bob / Bob12345!`.

Port 8000 is used on purpose — on macOS port 5000 is occupied by the AirPlay
Receiver, which answers every request with `403`. Override with `PORT=9000 python app.py`.

The repository is public; the file layout above is what the grader sees on the
landing page:

![public repository page](docs/screenshots/09-repo.png)

The same scanners the pipeline runs, locally:

```bash
mkdir -p reports
pytest -q --junitxml=reports/pytest.xml
bandit app.py init_db.py create_user.py -f json -o reports/bandit.json
pip-audit -r requirements.txt
```

---

## 2. API reference

| # | Method | Path | Auth | Purpose |
|---|---|---|---|---|
| 1 | POST | `/auth/login` | no | verify credentials, return a JWT |
| 2 | GET | `/api/data` | Bearer JWT | list posts, optional `?q=` substring filter |
| 3 | POST | `/api/data` | Bearer JWT | create a post (the third, self-chosen endpoint) |

The third endpoint is not filler: it is the write side of the data model, and it is
what makes a **stored** XSS demonstration possible end to end (inject → store →
render). Without it, XSS protection could only be asserted, not shown.

### 2.1 `POST /auth/login`

```bash
curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"Alice123!"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbGljZSIsImlhdCI6MTc5MjQ2MjcwNywiZXhwIjoxNzkyNDY0NTA3fQ.uKKvDeIlmRwji8LzRXFCCfvTh2_gklFtNUWkGApxg8o",
  "expires_in": 1800,
  "token_type": "Bearer"
}
```

A wrong password and an unknown user both return `401 {"error":"invalid credentials"}`
with one bcrypt comparison each, so neither the message nor the latency reveals
whether the account exists.

### 2.2 `GET /api/data`

```bash
curl -i http://127.0.0.1:8000/api/data
# HTTP/1.1 401 UNAUTHORIZED
# {"error":"missing bearer token"}

curl -s http://127.0.0.1:8000/api/data -H "Authorization: Bearer $TOKEN"
```

```json
[{"author":"alice","body":"First post from the seed data.","created_at":"2026-10-20T02:18:19.652757+00:00","id":"1","title":"Hello"}]
```

### 2.3 `POST /api/data`

```bash
curl -s -X POST http://127.0.0.1:8000/api/data \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"note","body":"hello"}'
# {"status":"created"}   -> HTTP 201
```

`400` when `title` is empty, `401` without a valid token. Both fields are truncated
to 200 characters so a client cannot store unbounded data.

### 2.4 Evidence — all three endpoints, plus the attack attempts

`secure-api/demo.sh` runs the whole sequence (`401` → `200` → SQLi payload →
stored XSS payload → escaped output → response headers):

![API demo: 401 without token, 200 with token, SQLi returns [], stored XSS is escaped on output](docs/screenshots/08-api-demo.png)

---

## 3. Implemented security measures

### 3.1 Protection against SQL injection — parameterised statements only

Every statement is a constant SQL string; user input is bound as a parameter, so it
can never change the parse tree of the query — quotes, comments and `UNION` tricks
lose their meaning:

```python
row = get_db().execute(
    "SELECT username, password_hash FROM users WHERE username = ?", (username,)
).fetchone()
```

The `LIKE` filter follows the same rule — the `%` wildcards are added to the *value*,
not to the statement, which is the detail usually got wrong when a search is added:

```python
pattern = f"%{query}%"
rows = get_db().execute(
    "SELECT id, author, title, body, created_at FROM posts "
    "WHERE title LIKE ? OR body LIKE ? ORDER BY id",
    (pattern, pattern),
).fetchall()
```

**Proof** — the classic payload `?q=' OR 1=1--` is treated as a literal search term,
so the endpoint returns an empty list instead of every row (see the `[]` in the demo
screenshot above, section 5).

### 3.2 Protection against XSS — output encoding

Content is stored exactly as the user typed it and encoded at the moment it is
returned. Output is the correct layer: the same value may later be rendered into
HTML, a log file or a PDF, and only the output context knows which encoding is
appropriate; escaping on input would corrupt the data and still be wrong elsewhere.

```python
return jsonify([{key: html.escape(str(row[key])) for key in row.keys()} for row in rows])
```

A stored `<script>alert(document.cookie)</script>` therefore comes back as
`&lt;script&gt;alert(document.cookie)&lt;/script&gt;`, and the response also carries
`Content-Type: application/json`, `X-Content-Type-Options: nosniff` and a restrictive
`Content-Security-Policy`, so a client that misuses the data cannot execute it.

### 3.3 Protection against broken authentication — bcrypt + JWT

* **Password storage.** `bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))`. bcrypt
  embeds a random per-user salt in the hash (identical passwords give different
  digests, precomputed tables are useless) and the cost factor makes each guess
  deliberately expensive. Plain SHA-256 would allow billions of guesses per second.
* **Token issuing.** On success the server signs `{"sub", "iat", "exp"}` with HS256
  and returns it; nothing is stored server-side, so the token is the credential.
* **Token verification.** A decorator guards every protected route and decodes with an
  explicit algorithm whitelist:

```python
payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
```

  The whitelist blocks both classic JWT attacks — `alg: none` (unsigned token) and
  algorithm confusion (an RS256 public key misused as an HMAC secret). Expired tokens
  raise `ExpiredSignatureError` → `401`.
* **Fail closed.** Missing, malformed, tampered or expired tokens all return `401`
  before any handler code runs.
* **No key in the repository.** `SECRET_KEY` is read from the environment; a random
  one is generated when it is absent.

| Attack | Control |
|---|---|
| Credential stuffing / offline cracking | bcrypt, cost 12, per-user salt |
| User enumeration | identical error message and comparable latency |
| Signature forgery | HS256 signature verified on every request |
| `alg: none` / algorithm confusion | explicit `algorithms=[...]` whitelist |
| Stolen token replay | 30-minute expiry |
| Unauthorised access to data | decorator on every protected route (fail closed) |

### 3.4 Response hardening

```python
response.headers["X-Content-Type-Options"] = "nosniff"
response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
response.headers["Referrer-Policy"] = "no-referrer"
response.headers["Cache-Control"] = "no-store"
```

---

## 4. CI/CD pipeline with security scanners

`.github/workflows/ci.yml` runs on **every push and every pull request**. The job is
called **Tests, SAST, and SCA** and its steps mirror what a reviewer would do by hand:

| Step | What it actually does |
|---|---|
| Check out project / Set up Python | checkout, Python 3.11 with a pip cache |
| Install application and security tools | `pip install -r requirements.txt bandit pip-audit pytest`, then verifies the runtime imports and prints both scanner versions |
| Prepare isolated CI configuration | writes `.env.ci` with a throwaway `SECRET_KEY`, a database in `$RUNNER_TEMP` and memory journal mode — a developer's local configuration can never leak into CI, and nothing is left on the runner |
| Run API and security regression tests | `pytest --junitxml=reports/pytest.xml`, then a **live smoke test** of the running server: 401 without a token → login → 200 with the token → injection payload returns 200 and no rows |
| SAST - scan application source with Bandit | `python -m bandit app.py init_db.py create_user.py -f json -o reports/bandit.json` |
| SCA - audit application dependencies | `python -m pip_audit -r requirements.txt -f json -o reports/pip-audit.json` |
| Summarize results | reads the three machine-readable reports and writes **one written conclusion** to the run's Summary page; the step fails the build if any control broke |
| Save test and security reports | uploads `secure-api/reports/` (4 files) as the `security-reports` artifact |

Every step is named and its log is readable without opening the YAML, because the
pipeline is meant to be *audited*, not just executed. The smoke test matters: the unit
tests use Flask's test client, which bypasses the socket, so "12 green tests" alone
would not prove that the deployed server enforces the same rules.

Last successful run (commit `ab2f068`, all 13 rows green, 39 s):
**[github.com/kanloner/information_security/actions/runs/39544635930](https://github.com/kanloner/information_security/actions/runs/39544635930)**

The run ends with a conclusion instead of a wall of log lines:

```
## Tests, SAST, and SCA - conclusion

- **bandit (SAST)**: 0 finding(s) - none
- **pip-audit (SCA)**: 9 pinned dependencies audited, 0 known vulnerability(ies)
- **pytest**: 12 tests, 0 failures, 0 errors (9.3s of test time)

**Conclusion:** every control held - the build is safe to merge.
```

and the behavioural part of that conclusion is visible in the step above it:

```
12 passed in 9.70s
GET /api/data without a token -> HTTP 401 (expected 401)
POST /auth/login -> token issued (147 characters)
GET /api/data with a token -> HTTP 200 (expected 200)
GET /api/data?q=' OR 1=1-- -> HTTP 200 (payload treated as a literal)
```

![GitHub Actions - Tests, SAST and SCA all green](docs/screenshots/01-ci-green.png)

![bandit - no issues identified](docs/screenshots/02-bandit.png)

![pip-audit - no known vulnerabilities found](docs/screenshots/03-pip-audit.png)

`02-bandit.png` shows the `security-reports` artifact of a pipeline run and
`03-pip-audit.png` the SCA step of the same job. They were captured before the job was
split into the ten named steps listed above, so the labels inside them are shorter than
that list; the log of the current run is quoted in full above.

The same three commands were also executed locally before the first online run, so the
expected result of every step was known in advance:

```
$ bandit app.py init_db.py create_user.py -f txt
	Total lines of code: 286
	Total lines skipped (#nosec): 0
	No issues identified.

$ pip-audit -r requirements.txt
No known vulnerabilities found

$ pytest -q
............                                                             [100%]
12 passed in 8.57s
```

One finding had to be handled during the work: the first scan reported B105/B106
("possible hardcoded password: 'Bearer'") on the OAuth2 `token_type` field, because
bandit flags any key whose name contains `token` when bound to a string literal.
Suppressing it with `#nosec` would have hidden the class of issue the scanner exists to
find, so the value was moved into the named constant `AUTH_SCHEME` — and later into a
shared module, so the three scanned files stay at **zero skipped lines**. That number is
itself evidence that no finding was silenced.

---

## 5. Tests

`secure-api/tests/test_api.py` — 12 tests, one per security property rather than
one per function:

| Test | Property protected |
|---|---|
| `test_login_returns_jwt` | login issues a well-formed token |
| `test_login_wrong_password_is_rejected` | 401, no token issued |
| `test_login_unknown_user_is_rejected` | no user enumeration |
| `test_data_requires_token` | access control, fail closed |
| `test_data_rejects_tampered_token` | signature verification |
| `test_data_returns_rows_with_valid_token` | functionality (happy path) |
| `test_sql_injection_payload_returns_nothing` | parameterised queries |
| `test_stored_xss_is_escaped_on_output` | output encoding |
| `test_create_requires_token` | access control on writes |
| `test_create_validates_empty_title` | input validation |
| `test_security_headers_present` | response hardening |
| `test_create_user_adds_a_working_account` | account provisioning + password policy |

![pytest - 12 passed](docs/screenshots/10-pytest.png)

---

## 6. Selected vulnerability: CVE-2021-25646

| Field | Value |
|---|---|
| CVE | CVE-2021-25646 |
| Product | Apache Druid |
| Affected | <= 0.20.0 |
| Fixed | 0.20.1 |
| CVSS 3.1 | 8.8 High — `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` |
| CWE | CWE-732 — Incorrect Permission Assignment for Critical Resource |
| Authentication required | none (the console has no auth by default) |

Apache Druid can execute user-provided JavaScript embedded in ingestion requests.
The feature is meant for high-trust environments and is disabled by default, but in
Druid 0.20.0 and earlier a crafted JSON body containing an empty key (`""`)
overrides the `enabled` flag of the JavaScript parser, so the feature runs regardless
of configuration. The `function` field is then evaluated by the built-in Rhino
engine, where `java.lang.Runtime.getRuntime().exec()` executes arbitrary system
commands with the privileges of the Druid server process.

---

## 7. Reproducing the attack

```bash
# the vulnerable environment shipped with this repository (Druid 0.20.0)
cd secure-api/cve/CVE-2021-25646
docker compose up -d
docker compose ps                     # wait for "running", ~30 s

./reproduce.sh
```

or the single request that matters:

```bash
curl -s -X POST http://127.0.0.1:8888/druid/indexer/v1/sampler \
  -H "Content-Type: application/json" --data '<crafted JSON - see reproduce.sh>'
```

![docker compose ps - vulnerable Druid 0.20.0 container running](docs/screenshots/04-docker-ps.png)

![the sampler executes id and cat /etc/passwd through the Rhino engine](docs/screenshots/05-druid-rce.png)

The response contains the output of `id` — `uid=0(root) gid=0(root) groups=0(root)`
— proving arbitrary command execution as **root** inside the container. The same
primitive reads `/etc/passwd`, and the returned JSON echoes the file contents
verbatim, so the exfiltration needs no extra step.

> **Why the empty key matters.** The `parseSpec` object normally rejects JavaScript
> when the feature is disabled. The crafted body adds `"": {"enabled": "true"}` —
> an object with the *empty string* as a key — which the Jackson deserializer merges
> into the configuration map and which overrides the guard. That single field is the
> whole vulnerability.

---

## 8. Root cause analysis

The defect is not a single mistyped line. It is the combination of a dangerous
feature, a broken configuration guard and a reachable endpoint. Five points explain
it completely.

1. **A feature that is off by default.** Druid's JavaScript parsing is disabled
   unless the operator opts in. The design intent is that untrusted clients can never
   reach the engine — the guard is a configuration flag, not an authentication check.
2. **An empty-key override defeats the guard.** The `parseSpec` object is
   deserialised by Jackson into a configuration map. A JSON object with the empty
   string `""` as a key was accepted and merged into the map, overwriting the
   `enabled` flag, so a request could switch the feature back on. A single
   unvalidated map key downgraded a hard configuration guarantee into a
   client-controlled suggestion (CWE-732).
3. **The engine has no sandbox.** Once enabled, the `function` field is handed to the
   Rhino JavaScript engine, which runs inside the JVM and exposes `java.lang.Runtime`,
   so JavaScript can start native processes with the same privileges as the server.
   Nothing about the feature was designed for hostile input.
4. **No authentication on the console.** The sampler endpoint is reachable without
   any credentials, which turns "a feature that should be off" into unauthenticated
   remote code execution. Even where authentication exists, the override would still
   let any low-privileged user execute commands.
5. **The patch confirms the analysis.** 0.20.1 rejects the empty-key override, so the
   JavaScript feature can no longer be forced on by a request — the `function` field
   is never evaluated when the feature is disabled. The fix removes the root cause
   (the accepted override) rather than filtering payloads.

---

## 9. Applied fix

The correct remediation is to run a version that contains the patch — the image in
the compose file changes from 0.20.0 to 0.20.1, kept in [`secure-api/fixes/`](secure-api/fixes/):

```diff
 services:
   druid:
-    image: vulhub/apache-druid:0.20.0
+    build:
+      context: .
+      dockerfile: Dockerfile     # builds a 0.20.1 image (see below)
```

Why a Dockerfile instead of a plain tag: the official `apache/druid:0.20.1` image is
built on a **distroless** base that cannot run the `start-nano-quickstart` launcher
(it has neither `bash` nor `perl`, which the launcher scripts require). To keep both
environments comparable — same launcher, same embedded ZooKeeper, same ports —
`fixes/Dockerfile` keeps the vulhub 0.20.0 base (which provides those tools) and
replaces only the vulnerable `0.20.0` jars with the fixed `0.20.1` jars copied from
the official image. The result is a 0.20.1 server that starts identically to the
vulnerable one.

Why this is effective: the vulnerable behaviour was the accepted empty-key override.
In 0.20.1 the override is rejected, so the `function` field of a sampler request is
never passed to the Rhino engine, and `java.lang.Runtime` can no longer be reached —
the primitive disappears instead of being filtered.

---

## 10. Proof that the vulnerability is eliminated

The same request that executed `id` as root on 0.20.0 is replayed against 0.20.1,
followed by the regression checks — a fix that breaks the product is not a fix:

```bash
cd secure-api/cve/CVE-2021-25646
./verify_fix.sh http://127.0.0.1:8888
```

![the same request now returns JavaScript is disabled](docs/screenshots/06-druid-fixed.png)

![regression: the fixed container reports version 0.20.1 and the console responds](docs/screenshots/07-druid-regression.png)

```
== 1. Replay the exploit (must NOT execute the command)
   body: {"error":"Failed to sample data: JavaScript is disabled"}
   [PASS] no command output - the JavaScript feature is disabled

== 2. Regression: the Druid console still responds
   GET / -> HTTP 302

RESULT: fix verified, service healthy.
```

The regression check also queries `GET /status`, which reports
`"version":"0.20.1"` — confirming the replay really ran against the patched server.

---

## 11. Screenshots index

| File | Content |
|---|---|
| `01-ci-green.png` | Actions page, last run with all steps green |
| `02-bandit.png` | bandit output: `No issues identified` |
| `03-pip-audit.png` | pip-audit: `No known vulnerabilities found` |
| `04-docker-ps.png` | `docker compose ps` — vulnerable container running |
| `05-druid-rce.png` | the sampler executes `id` and `cat /etc/passwd` as root |
| `06-druid-fixed.png` | the same request after the fix: `JavaScript is disabled` |
| `07-druid-regression.png` | regression: `/status` reports 0.20.1, console `302` |
| `08-api-demo.png` | 401 / 200 / SQLi `[]` / escaped XSS / security headers |
| `09-repo.png` | public repository page |
| `10-pytest.png` | `pytest -q` — 11 passed |

---

## 12. Notes and limitations

* SQLite is used for simplicity. With PostgreSQL the same parameterised-query rule
  applies identically (`%s` placeholders or an ORM).
* JWT is stateless, so logout/revocation needs a short TTL plus a denylist; the
  30-minute TTL is a deliberate compromise for this exercise.
* The fixed Druid image is built from `fixes/Dockerfile` (vulhub base + 0.20.1 jars)
  because the official 0.20.1 image is distroless and cannot run the single-server
  launcher; both images are `linux/amd64`.
