#!/usr/bin/env bash
# End-to-end API demonstration - produces exactly the evidence the report needs.
# Start the server first:  ./.venv/bin/python app.py
#
# set -u  : an unset variable is an error (catches a typo in $TOKEN)
# set -o pipefail : a failing command inside a pipeline fails the pipeline
# There is deliberately no "set -e": several steps *expect* a 401, and the
# script must keep going to show the contrast between the rejected and the
# accepted request.
set -uo pipefail

# ${1:-default} - use the first argument if given, otherwise the local server.
# This is what lets the same script be pointed at a deployed instance.
BASE="${1:-http://127.0.0.1:8000}"
hr() { printf '\n%s\n' "------------------------------------------------------------"; }

hr; echo "1. POST /auth/login  (valid credentials)"
# -s silences the progress bar so the JSON can be captured cleanly.
LOGIN_JSON=$(curl -s -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"Alice123!"}')
echo "$LOGIN_JSON"
# Token extraction without jq (the script must run on a bare runner):
#   tr ',' '\n'      split the one-line JSON into one field per line
#   grep -o '...'    keep only the quoted value after "access_token"
#   cut -d'"' -f4    take the 4th double-quote-delimited field
# Fragile by design, but this is a demo script, not the test suite.
TOKEN=$(printf '%s' "$LOGIN_JSON" | tr ',' '\n' | grep -o '"access_token"[^,}]*' | cut -d'"' -f4)
# ${TOKEN:0:40} truncates: printing the whole token would fill the screen and
# is pointless, but showing the prefix proves a token really was issued.
echo "token: ${TOKEN:0:40}..."

hr; echo "2. POST /auth/login  (wrong password -> 401)"
# -o /dev/null discards the body, -w prints only the status code: the point of
# this step is the number, not the JSON.
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"wrong"}'

hr; echo "3. GET /api/data  (no token -> 401)"
# -i keeps the response headers, then head -n 1 shows just the status line.
curl -s -i "$BASE/api/data" | head -n 1
curl -s "$BASE/api/data"

hr; echo "4. GET /api/data  (valid token -> 200)"
curl -s -i -H "Authorization: Bearer $TOKEN" "$BASE/api/data" | head -n 1
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/data"

hr; echo "5. SQL injection attempt: ?q=' OR 1=1--   (returns [] -> parameterised)"
# %27 %20 %3D are ' space and = . The payload is passed as data, so it is
# compared as a literal string and matches nothing - hence [].
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/data?q=%27%20OR%201%3D1--"

hr; echo "6. POST /api/data  (store an XSS payload)"
curl -s -X POST "$BASE/api/data" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"xss-demo","body":"<script>alert(document.cookie)</script>"}'

hr; echo "7. GET /api/data?q=xss-demo   (payload is escaped on output)"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/data?q=xss-demo"

hr; echo "8. Response headers on a protected route"
# -D - writes the headers to stdout while -o /dev/null drops the body, which is
# how the nosniff / CSP / no-store lines become visible.
curl -s -D - -o /dev/null -H "Authorization: Bearer $TOKEN" "$BASE/api/data"

hr; echo "done"
