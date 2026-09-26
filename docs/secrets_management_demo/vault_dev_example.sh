#!/usr/bin/env bash
# Real, runnable demonstration of writing and reading a secret from a local dev-mode Vault (see
# docker-compose.vault.yml), using nothing but curl against Vault's real HTTP API - so it needs no
# extra Python dependency in the 7 services this project already ships. Exits non-zero on any
# real failure so it can gate a CI job (see .github/workflows/vault-verify.yml), not just print
# output and hope. Adapted from this project's own sibling AMEX RiskIQ Enterprise Credit Risk
# Platform repo's real, already-verified-green vault_dev_example.sh (2026-09-26).
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-root-token-for-local-dev-only}"
SECRET_PATH="secret/data/customer360/services"
SECRET_KEY="c360_api_key"
SECRET_VALUE="dev-only-CHANGE-ME-before-deploying"

echo "Waiting for Vault to report healthy at ${VAULT_ADDR} ..."
for i in $(seq 1 15); do
  if curl -sf "${VAULT_ADDR}/v1/sys/health" > /dev/null; then
    echo "Vault is up (attempt ${i})."
    break
  fi
  if [ "${i}" -eq 15 ]; then
    echo "Vault never became healthy." >&2
    exit 1
  fi
  sleep 2
done

echo "Writing a real secret to ${SECRET_PATH} ..."
curl -sf \
  --header "X-Vault-Token: ${VAULT_TOKEN}" \
  --request POST \
  --data "{\"data\": {\"${SECRET_KEY}\": \"${SECRET_VALUE}\"}}" \
  "${VAULT_ADDR}/v1/${SECRET_PATH}" > /tmp/vault_write_response.json
cat /tmp/vault_write_response.json

echo "Reading the real secret back from ${SECRET_PATH} ..."
curl -sf \
  --header "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/${SECRET_PATH}" > /tmp/vault_read_response.json
cat /tmp/vault_read_response.json

echo "Verifying the value read back matches exactly what was written ..."
python3 -c "
import json
with open('/tmp/vault_read_response.json') as f:
    body = json.load(f)
actual = body['data']['data']['${SECRET_KEY}']
expected = '${SECRET_VALUE}'
assert actual == expected, f'Mismatch: wrote {expected!r}, read back {actual!r}'
print('Verified: value read back from Vault exactly matches what was written.')
"

echo "vault_dev_example.sh: PASSED"
