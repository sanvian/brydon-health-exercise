#!/usr/bin/env bash
# Isolation proof for the simulated single-tenant fleet.
#
# Three claims, each tested mechanically:
#   1. Every tenant serves ONLY its own data (same route, different subdomain,
#      different children).
#   2. Topology: a tenant's app cannot even resolve another tenant's database
#      hostname — the DBs live on private per-tenant networks.
#   3. Credentials: every tenant's Postgres has its own password; another
#      tenant's credentials are rejected outright.
#
# Run: make verify   (stack must be up)
set -euo pipefail
cd "$(dirname "$0")/.."

TENANTS=(riverside lakeside maple harborview sunrise)
BASE="brydon.localhost:8080"
pass() { printf '  \342\234\223 %s\n' "$1"; }
fail() { printf '  \342\234\227 FAIL: %s\n' "$1"; exit 1; }

echo "1) Each tenant serves only its own data"
for t in "${TENANTS[@]}"; do
  curl -sf "http://$t.$BASE/healthz" | grep -q "\"$t\"" \
    || fail "$t /healthz does not report tenant '$t'"
done
pass "all 5 tenants report their own tenant id"

rosters=$(for t in "${TENANTS[@]}"; do curl -sf "http://$t.$BASE/patients" | cksum; done)
[ "$(echo "$rosters" | sort -u | wc -l)" -eq 5 ] \
  || fail "two tenants returned identical patient rosters"
pass "all 5 patient rosters are distinct"

curl -sf "http://riverside.$BASE/patients" | grep -q "Nguyen" \
  || fail "riverside roster missing its own patient"
curl -sf "http://riverside.$BASE/patients" | grep -q "Petrov" \
  && fail "riverside roster contains a LAKESIDE patient" || true
pass "riverside sees Nguyen (its own), never Petrov (lakeside's)"

echo "2) Topology: cross-tenant databases are unreachable"
docker compose exec -T app-riverside python3 - <<'PY' || exit 1
import socket
try:
    socket.getaddrinfo("db-lakeside", 5432)
    raise SystemExit("  ✗ FAIL: app-riverside can resolve db-lakeside")
except socket.gaierror:
    pass
socket.create_connection(("db-riverside", 5432), timeout=3).close()
print("  ✓ app-riverside reaches db-riverside, cannot even resolve db-lakeside")
PY

echo "3) Credentials: one tenant's password is useless at another's database"
# Must test over the NETWORK: inside the db container, localhost connections
# hit postgres's default trust rule and no password is checked at all.
docker compose exec -T app-lakeside python3 - <<'PY' || exit 1
import psycopg
try:
    psycopg.connect("postgresql://ehr:ehr_riverside_pw@db-lakeside:5432/ehr",
                    connect_timeout=3)
    raise SystemExit("  ✗ FAIL: db-lakeside accepted RIVERSIDE's password")
except psycopg.OperationalError as e:
    assert "password authentication failed" in str(e), e
print("  ✓ db-lakeside rejects riverside's credentials (password auth failed)")
PY

echo
echo "Isolation verified: distinct data, unroutable cross-tenant DBs, per-tenant credentials."
