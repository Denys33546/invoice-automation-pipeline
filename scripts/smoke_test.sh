#!/usr/bin/env bash
# Smoke test for a running Invoice Extractor API.
# Usage: scripts/smoke_test.sh [BASE_URL] [API_KEY]
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
API_KEY="${2:-}"
SAMPLES="$(cd "$(dirname "$0")/../samples" && pwd)"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok    $*"; }

# post FILE [curl options...]  ->  prints the body, then the HTTP status on the last line
post() {
  local file="$1"
  shift
  curl -s -m 20 -w '\n%{http_code}' ${1+"$@"} -F "file=@${file}" "${BASE_URL}/extract"
}

echo "Waiting for ${BASE_URL}/health ..."
for _ in $(seq 1 30); do
  curl -sf -m 3 "${BASE_URL}/health" >/dev/null && break
  sleep 1
done
curl -sf -m 3 "${BASE_URL}/health" | tr -d '[:space:]' | grep -q '"status":"ok"' \
  || fail "/health did not answer ok"
pass "/health answers ok"

key_option=()
if [ -n "$API_KEY" ]; then
  code="$(curl -s -m 20 -o /dev/null -w '%{http_code}' \
    -F "file=@${SAMPLES}/invoice_0001.pdf" "${BASE_URL}/extract")"
  [ "$code" = "401" ] || fail "a request without the key must give 401, got ${code}"
  pass "a request without the key is rejected (401)"
  key_option=(-H "X-API-Key: ${API_KEY}")
fi

# run one sample and keep status, readable body and a whitespace-free body for exact JSON checks
run_sample() {
  local response
  response="$(post "${SAMPLES}/$1" ${key_option[@]+"${key_option[@]}"})"
  status="$(printf '%s\n' "$response" | tail -n1)"
  body="$(printf '%s\n' "$response" | sed '$d')"
  compact="$(printf '%s' "$body" | tr -d '[:space:]')"
  [ "$status" = "200" ] || fail "$1: expected HTTP 200, got ${status}"
}

run_sample invoice_0001.pdf
printf '%s' "$compact" | grep -q '"valid":true' || fail "invoice_0001.pdf should be valid: $body"
printf '%s' "$compact" | grep -q '"number":"INV-2026-0001"' || fail "wrong invoice number: $body"
printf '%s' "$compact" | grep -q '"total":"84.24"' || fail "wrong total: $body"
pass "a good invoice is extracted (INV-2026-0001, total 84.24)"

run_sample problem_wrong_total.pdf
printf '%s' "$compact" | grep -q '"valid":false' || fail "a wrong total must be flagged: $body"
printf '%s' "$body" | grep -q 'Subtotal + tax' || fail "the reason is missing: $body"
pass "an invoice with a wrong total is flagged"

run_sample problem_not_a_pdf.pdf
printf '%s' "$compact" | grep -q '"valid":false' || fail "a broken file must be flagged: $body"
printf '%s' "$body" | grep -q 'Could not read PDF' || fail "the reason is missing: $body"
pass "a file that is not a PDF is reported, not an HTTP error"

echo "All smoke tests passed."