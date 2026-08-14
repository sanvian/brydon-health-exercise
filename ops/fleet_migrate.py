"""Fleet migration runner — the bonus problem.

The problem this solves: with N fully isolated single-tenant deployments,
every schema change is N separate migrations, and nothing forces them to
happen together. Two tenants a version apart is silent until an app deploy
assumes a column that one database doesn't have — version DRIFT is the
operational tax of the single-tenant model, and it grows linearly with
sales. ("The code bases are identical — we are told." This tool is how you
KNOW, for the schema at least.)

What it does:
  status  — per-tenant schema version + drift warning, read-only
  apply   — bring tenants up to date, in order, one transaction per
            migration per tenant; --tenant limits scope (canary or drift
            demo). A failure stops that tenant at its last good version
            and reports it — the fleet never half-applies a migration.

Access path: `docker compose exec db-<t> psql`, because the tenant DBs
publish no ports and live on private networks — the same constraint the
real MSP-hosted fleet would impose (per-deployment access, no shared
connection plane). Migrations are plain numbered SQL files in
ops/migrations/, applied in filename order, recorded in a per-tenant
schema_migrations ledger.

Try the drift story:
    make fleet-status                          # all at version 0
    python3 ops/fleet_migrate.py apply --tenant riverside
    make fleet-status                          # DRIFT: riverside ahead
    make fleet-migrate                         # converge the fleet
"""

import argparse
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
MIGRATIONS_DIR = HERE / "migrations"
TENANTS = ["riverside", "lakeside", "maple", "harborview", "sunrise"]

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY,
    name text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def psql(tenant: str, sql: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "exec", "-T", f"db-{tenant}",
         "psql", "-U", "ehr", "-d", "ehr", "-v", "ON_ERROR_STOP=1",
         "--quiet", "--no-align", "--tuples-only", *flags],
        input=sql, capture_output=True, text=True, cwd=HERE.parent,
    )


def migrations() -> list[tuple[int, str, pathlib.Path]]:
    out = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"(\d+)_(.+)\.sql$", f.name)
        if not m:
            sys.exit(f"bad migration filename (want NNNN_name.sql): {f.name}")
        out.append((int(m.group(1)), m.group(2), f))
    return out


def current_version(tenant: str) -> int:
    r = psql(tenant, LEDGER_DDL + "SELECT coalesce(max(version), 0) FROM schema_migrations;")
    if r.returncode != 0:
        sys.exit(f"{tenant}: cannot read schema version — is the stack up?\n{r.stderr}")
    return int(r.stdout.strip())


def cmd_status(tenants: list[str]) -> None:
    latest = max((v for v, _, _ in migrations()), default=0)
    versions = {t: current_version(t) for t in tenants}
    print(f"{'tenant':<12} {'version':>7}   (latest available: {latest:04d})")
    for t, v in versions.items():
        lag = "" if v == latest else f"  <- behind by {latest - v}"
        print(f"{t:<12} {f'{v:04d}':>7}{lag}")
    if len(set(versions.values())) > 1:
        print("\nDRIFT: fleet is not at a uniform schema version.")
        sys.exit(2)
    if set(versions.values()) == {latest}:
        print("\nFleet is uniform and current.")
    else:
        print("\nFleet is uniform but behind — run 'make fleet-migrate'.")


def cmd_apply(tenants: list[str]) -> None:
    failed = False
    for t in tenants:
        v = current_version(t)
        pending = [(n, name, f) for n, name, f in migrations() if n > v]
        if not pending:
            print(f"{t}: up to date at {v:04d}")
            continue
        for n, name, f in pending:
            sql = (
                f.read_text()
                + f"\nINSERT INTO schema_migrations (version, name) VALUES ({n}, '{name}');\n"
            )
            # --single-transaction: the migration and its ledger row land
            # together or not at all; a failure leaves the tenant at its
            # last good version instead of half-migrated.
            r = psql(t, sql, "--single-transaction")
            if r.returncode != 0:
                print(f"{t}: FAILED at {n:04d}_{name} — stopped at {v:04d}")
                print("    " + r.stderr.strip().replace("\n", "\n    "))
                failed = True
                break
            v = n
            print(f"{t}: applied {n:04d}_{name}")
    if failed:
        sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=["status", "apply"])
    p.add_argument("--tenant", choices=TENANTS, help="limit to one tenant (canary / drift demo)")
    args = p.parse_args()
    tenants = [args.tenant] if args.tenant else TENANTS
    (cmd_status if args.command == "status" else cmd_apply)(tenants)


if __name__ == "__main__":
    main()
