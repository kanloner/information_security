#!/usr/bin/env bash
# End-to-end API demonstration - produces exactly the evidence the report needs.
# Start the server first:  ./.venv/bin/python app.py
set -uo pipefail

BASE="${1:-http://127.0.0.1:8000}"
hr() { printf '\n%s\n' "------------------------------------------------------------"; }

hr; echo "1. POST /auth/login  (valid credentials)"
LOGIN_JSON=$(curl -s -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"Alice123!"}')
echo "$LOGIN_JSON"
TOKEN=$(printf '%s' "$LOGIN_JSON" | tr ',' '\n' | grep -o '"access_token"[^,}]*' | cut -d'"' -f4)
echo "token: ${TOKEN:0:40}..."

hr; echo "2. POST /auth/login  (wrong password -> 401)"
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"wrong"}'

hr; echo "3. GET /api/data  (no token -> 401)"
curl -s -i "$BASE/api/data" | head -n 1
curl -s "$BASE/api/data"

hr; echo "4. GET /api/data  (valid token -> 200)"
curl -s -i -H "Authorization: Bearer $TOKEN" "$BASE/api/data" | head -n 1
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/data"

hr; echo "5. SQL injection attempt: ?q=' OR 1=1--   (returns [] -> parameterised)"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/data?q=%27%20OR%201%3D1--"

hr; echo "6. POST /api/data  (store an XSS payload)"
curl -s -X POST "$BASE/api/data" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"xss-demo","body":"<script>alert(document.cookie)</script>"}'

hr; echo "7. GET /api/data?q=xss-demo   (payload is escaped on output)"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/data?q=xss-demo"

hr; echo "8. Response headers on a protected route"
curl -s -D - -o /dev/null -H "Authorization: Bearer $TOKEN" "$BASE/api/data"

hr; echo "done"
