#!/bin/sh
# Example client for the seo-builder API.
#   ./client/example.sh                      -> build only
#   DEPLOY=1 ./client/example.sh             -> build + upload to the panel
#   WAIT=1 ./client/example.sh               -> hold the connection until done
set -eu

BUILDER_URL="${BUILDER_URL:-https://localhost:8443}"
API_TOKEN="${API_TOKEN:?export API_TOKEN}"
CURL_FLAGS=""
[ "${INSECURE:-1}" = "1" ] && CURL_FLAGS="-k"   # internal TLS: skip verification

BRAND="${BRAND:-Infinity Shop}"
LANG_="${LANG:-en}"
CC="${CC:-CZ}"
GEO="${GEO:-Praha}"
CURRENCY="${CURRENCY:-CZK}"
DOMAIN="${DOMAIN:-infinity-shop.site}"
DEPLOY="${DEPLOY:-0}"
WAIT="${WAIT:-0}"

PAYLOAD=$(cat <<EOF
{
  "brand": "${BRAND}",
  "lang": "${LANG_}",
  "cc": "${CC}",
  "geo": "${GEO}",
  "currency": "${CURRENCY}",
  "domain": "${DOMAIN}",
  "with_llm": true,
  "deploy": ${DEPLOY},
  "wait": ${WAIT}
}
EOF
)

echo ">> POST ${BUILDER_URL}/build"
RESP=$(curl $CURL_FLAGS -sS -X POST "${BUILDER_URL}/build" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")
echo "${RESP}"

JOB_ID=$(printf '%s' "${RESP}" | sed -n 's/.*"job_id"[[:space:]]*:[[:space:]]*"\([a-f0-9-]*\)".*/\1/p' | head -1)
[ -n "${JOB_ID}" ] || exit 0

echo ">> polling /jobs/${JOB_ID}"
while :; do
  sleep 5
  R=$(curl $CURL_FLAGS -sS "${BUILDER_URL}/jobs/${JOB_ID}" \
      -H "Authorization: Bearer ${API_TOKEN}")
  S=$(printf '%s' "${R}" | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' | head -1)
  echo "   status: ${S}"
  case "${S}" in done|failed) echo "${R}"; break;; esac
done
