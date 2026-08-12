# Brydon Health — Multi-Tenant Architecture Exercise

One mechanism, applied twice: a minimal **tenant directory** (control plane)
that resolves `hash(email) → tenant`, wrapped in an anti-enumeration flow.
The patient portal and the marketing "Log In" link are the same problem —
*tenant discovery without tenant disclosure* — so they share one solution.

## How to run

```bash
make up        # builds and starts everything
```

| URL | What it is |
|---|---|
| http://www.brydon.localhost:8080 | Marketing site (single Log In link) |
| http://portal.brydon.localhost:8080 | Patient portal discovery |
| http://localhost:8025 | Mailpit — magic-link emails land here |
| http://riverside.brydon.localhost:8080 | Tenant instance (also: lakeside, maple, harborview, sunrise) |

Try it: enter `ava.parent@example.com` in the portal, open Mailpit, click the
link, land in Riverside. Then try `guardian.two-clinics@example.com` — a
parent with children at two practices — and note the email offers both.
Then try an email that doesn't exist and observe the identical response.

## Architecture

<!-- TODO: diagram + one paragraph. Key components:
     proxy (edge/DNS stand-in) · 5 isolated tenant stacks (own app, own
     Postgres instance, own credentials) · directory service (control
     plane) · Mailpit (email channel). -->

### Why isolation is real here
Each tenant has its own Postgres *instance* with its own credentials; no
application code path can reach another tenant's database. Isolation is
enforced by topology, not by WHERE clauses.

### The tenant directory: deliberate minimalism
The directory is the first piece of shared infrastructure in an architecture
whose value proposition is isolation — that's a compliance-relevant decision,
not a plumbing detail. Mitigations:
- Stores only `hash(email) → tenant_id`. No names, no PHI, no tenant data.
- Email is hashed with a peppered SHA-256; a directory breach yields no
  usable customer list without the pepper. <!-- TODO: expand -->
- Existence of an account is only ever revealed *inside the email channel*,
  which the requester must already control.

### Anti-enumeration posture
- Identical response body for hit and miss.
- <!-- TODO: constant-time behavior, rate limiting, single-use tokens,
     15-min expiry — fill in as implemented. -->

## Decisions & tradeoffs

<!-- TODO as built. Candidates:
- Magic link (email round-trip) for patients vs. direct redirect for
  providers — friction vs. disclosure tradeoff per audience.
- 5 Postgres instances vs. 5 schemas: chose instances for literal fidelity
  to "own dedicated database"; cost is memory footprint.
- Directory sync model: push-on-CRUD from tenants (simulated by seed file).
- Considered and rejected HAPI FHIR as the base: front-loads operational
  complexity into the part not being evaluated, and its native partitioning
  would bypass the single-tenant constraint the exercise asks to simulate.
  Data is FHIR R4-shaped instead (see seeds/generate.py).
-->

## Assumptions

<!-- TODO. Candidates:
- Email is the discovery key; guardians (not children) hold portal accounts.
- One email may map to multiple tenants (handled — see two-clinics case).
- Real auth (passwords/MFA/sessions) is out of scope; the handoff token
  proves tenant resolution, not identity.
-->

## Bonus: fleet operations problem

<!-- TODO: version drift across N single-tenant deployments; migration
     runner that applies schema changes across all tenants and reports
     per-tenant schema versions. -->

## Migration plan to multi-tenant

<!-- TODO: Phase 0 (this exercise): extract identity/discovery into a
     control plane. Phase 1: shared Postgres, schema-per-tenant. Phase 2:
     pooled tables + RLS for the small-customer tail; keep dedicated
     schemas for enterprise/compliance-sensitive accounts. Per phase:
     isolation guarantee preserved, rollback mechanism (dual-write window,
     per-tenant cutover, old deployment kept warm), and the honest risk
     statement: a bad RLS policy is a breach, not a bug. -->

## What I'd do differently with more time

<!-- TODO -->
