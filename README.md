# Brydon Health — Multi-Tenant Architecture Exercise

One mechanism, applied twice: a minimal **tenant directory** (control plane)
that resolves `hash(email) → (tenant, audience)`, wrapped in the right
disclosure posture for each audience. The patient portal and the marketing
"Log In" link are the same underlying problem — *tenant discovery without
tenant disclosure* — so they share one index and one redeem endpoint, with
different policies on top.

The rule everything follows: **the shared layer resolves *where*; only the
tenant's own origin ever sees proof of *who*.** No password, and no
authentication decision, ever passes through shared infrastructure.

## How to run

```bash
make up        # builds and starts everything
```

| URL | What it is |
|---|---|
| http://www.brydon.localhost:8080 | Marketing site (single provider Log In) |
| http://portal.brydon.localhost:8080 | Patient portal discovery |
| http://localhost:8025 | Mailpit — sign-in and reminder emails land here |
| http://riverside.brydon.localhost:8080 | Tenant instance (also: lakeside, maple, harborview, sunrise) |

### Try it

1. **Patient discovery.** Enter `ava.parent@example.com` in the portal, open
   Mailpit, click the link → you land on Riverside's own sign-in page, with a
   "routed by the portal" banner (the handoff token verified). Click the same
   emailed link again → "no longer valid" (single-use).
2. **A parent with children at two practices.** Try
   `guardian.two-clinics@example.com` — one email arrives offering both
   Riverside and Lakeside.
3. **Anti-enumeration.** Try `nobody@example.com` — the response is
   byte-for-byte identical to a hit, and no email is sent.
4. **Provider login.** On the marketing site, enter
   `office@lakesidepediatrics.com` → immediate redirect to Lakeside's staff
   sign-in. Try `lakesidepedsoffice@gmail.com` — same result: audience comes
   from the directory record, not the email's domain.
5. **One person, two roles.** `dr.chen@riversidepeds.com` is staff at
   Riverside and a parent at Lakeside. Via the marketing form: straight to
   Riverside staff login. Via the patient portal: an email offering both,
   labeled.
6. **Reminder deep links.** `make remind` simulates Riverside's reminder job:
   a pre-signed link lands in Mailpit that skips discovery entirely — one
   click to Riverside's sign-in page, reusable for days.
7. **Isolation proof.** `make verify` — distinct rosters per tenant,
   cross-tenant DB hostnames unresolvable, cross-tenant credentials rejected.

## Architecture

```
                        ┌─ www.*  ──────► marketing (static)
 browser ──► Caddy ─────┼─ portal.* ────► directory (control plane) ──► Mailpit
 (*.brydon.localhost)   └─ {tenant}.* ──► app-{tenant} ──► db-{tenant}
                                            × 5, fully isolated stacks
```

Five tenants, each a genuinely isolated deployment: its own app container and
its own Postgres *instance*, with its own password, on its own **private
compose network** that only that tenant's app joins. Isolation is enforced by
topology, not by WHERE clauses: `app-riverside` cannot even resolve
`db-lakeside`'s hostname, and lakeside's Postgres rejects riverside's
credentials. `make verify` proves all three properties mechanically
(`scripts/verify_isolation.sh`). Caddy stands in for DNS/edge routing. The
only shared services are the proxy, Mailpit (the email channel), and the
directory.

### The tenant directory: deliberate minimalism

The directory is the first piece of shared infrastructure in an architecture
whose value proposition is isolation — a compliance-relevant decision, not a
plumbing detail. It stores exactly two things:

```
email_index:  sha256(pepper + lowercase(email)) → tenant_id, audience
tenants:      tenant_id → display name (the customer list — server-side only)
```

- **No PHI, no names, no credentials, no plaintext emails.** A breach of the
  directory yields salted hashes pointing at opaque tenant IDs.
- **The pepper lives outside the datastore** (env / secret manager). Emails
  have tiny entropy, so an *unpeppered* hash index is reversible by anyone
  with a dictionary of addresses — it would be the customer list with one
  extra step. With the pepper held separately, a database dump alone is
  useless. Cost: no lookup-by-plaintext for ops, and rotating the pepper
  means re-syncing the index from tenants.
- **`audience` is stored, not inferred from the email's domain.** Small
  practices put staff on consumer domains (see
  `lakesidepedsoffice@gmail.com`), one person can be staff at one clinic and
  a parent at another (see `dr.chen@riversidepeds.com`), and domain-based
  *behavior* would let an attacker confirm customers by probing guessable
  addresses (`info@<clinic>.com`). The tenant's EHR already knows which
  accounts are staff; the sync feed carries that fact along.
- **Sync model:** each tenant pushes add/remove events on portal-user CRUD
  over mTLS; the directory hashes on ingest and discards plaintext. Simulated
  here by `seeds/directory_seed.json`. Consistency is eventual and the
  failure mode is benign: a stale entry means a silent miss or a dead link,
  never wrong-tenant access — landing at a tenant still requires that
  tenant's own login.

### The three flows

**Patients (deliverable 2).** Enter an email at the single portal URL → the
response is uniform for hit and miss → on a hit, an email arrives with one
link per (tenant, role) → the link redeems at the directory (signature,
expiry, single-use) → redirect to the clinic's **own sign-in page** with a
fresh 60-second handoff token proving the routing came from the directory.
The email→clinic mapping is health information ("this family attends
pediatric therapy at Riverside"), so it is only ever revealed inside an inbox
the requester already controls.

**Providers (deliverable 3).** The marketing "Log In" posts to the same
lookup with `audience=provider`. A registered staff email redirects
immediately to that clinic's staff login — home-realm discovery, the way
Microsoft 365 or Slack resolve a workspace. The disclosure is accepted
deliberately: staff emails are semi-public and mostly clinic-domain, so a
redirect reveals little, and only an *exact registered address* triggers
differential behavior. Unrecognized addresses degrade to the patient posture
(uniform page), and rate limiting blunts bulk probing.

**Reminder deep links (the PDF's automated-reminders hint).** The sender of a
reminder — the tenant's own EHR — already knows the tenant, so discovery
would be pointless friction. The tenant asks the directory to mint a
pre-signed deep link (`/internal/deep-link`, reachable only on the service
network; Caddy 404s it at the edge) and embeds it in the reminder email. One
click, straight to the clinic's sign-in page. The same works for clinic-run
email campaigns; a Brydon-wide campaign to an unresolved list just links the
bare portal URL and lets discovery handle each recipient.

### Tokens

| Token | Lifetime | Uses | Carries | Why |
|---|---|---|---|---|
| Discovery link | 15 min | 1 | tenant, audience, jti | Requested seconds ago; single-use kills replay/forwarding |
| Reminder link | 7 days | many | tenant, audience | Patients open reminder emails days later; routes to a login page, authenticates no one, so replay yields no access |
| Handoff | 60 s | — | tenant, audience | Proves to the tenant app that the directory did the routing; minted fresh at redeem, different signing salt |

All tokens are stateless signed payloads (`itsdangerous`); the directory
stores nothing about issued tokens except used discovery-link IDs (a set with
15-minute relevance — Redis TTL in a real deployment). Separate salts mean a
portal link can never be replayed as a handoff or vice versa. The handoff key
is symmetric app-wide for simulation simplicity; in the real product the
directory would sign asymmetrically and tenants would hold only the public key.

## Decisions & trade-offs (alternatives considered and rejected)

**Direct redirect for patients — rejected: it's an oracle.** "Type an email,
get redirected to the clinic" means anyone who knows an address can learn,
unauthenticated, that a family attends a specific pediatric therapy practice —
and a competitor can reconstruct the customer list one probe at a time. The
email round-trip closes exactly this: the clinic is only named inside the
inbox. The same trade *is* acceptable for providers (see above) because a
staff email's domain usually announces the clinic anyway — which is why the
design splits by audience instead of picking one posture for both.

**Magic-link *authentication* — rejected on HIPAA/privacy grounds.** Clicking
an emailed link must not log anyone in: inboxes are shared within families
(especially guardian accounts), links get forwarded, and inbox access is a
weak proxy for identity. Real portals (e.g. MyChart) use credentials + MFA.
So the emailed link here does **discovery only** — it lands on the clinic's
login page, where the tenant's own auth (out of scope, simulated) takes over.
Clinics email portal deep links routinely; what's non-standard is
auth-by-click, which this design deliberately avoids.

**Central authentication (portal calls each tenant's auth API) — rejected.**
It would function, but: (1) credentials *transit* the shared portal even if
stored per-tenant, making it the single point whose compromise harvests every
customer's passwords at once — the exact blast-radius the single-tenant
architecture exists to avoid; (2) passkeys/WebAuthn are origin-bound and
cannot work from a central form, locking the fleet onto passwords forever;
(3) fanning out auth calls amplifies one probe into N backend attempts and
makes login latency the slowest tenant in the fleet; (4) the success path
needs a signed assertion the tenant trusts — a homegrown SSO protocol — at
which point redirect-based flows (what OIDC does) are strictly simpler and
never touch the password; (5) bcrypt timing on hits reopens the enumeration
channel; (6) it trains patients to type clinic credentials into a non-clinic
domain. The redirect handoff achieves the same single entry point with none
of this.

**Instances vs. schemas: five Postgres instances.** Chosen for literal
fidelity to "own dedicated database" — isolation by topology and credentials,
which is the property a migration must preserve. Cost: memory footprint.

**HAPI FHIR as the base — rejected.** It front-loads operational complexity
into the part not being evaluated, and its native partitioning would bypass
the single-tenant constraint the exercise asks to simulate. Data is FHIR
R4-shaped instead (`seeds/generate.py`).

## Assumptions

- Email is the discovery key; guardians (not children) hold portal accounts —
  pediatric context.
- One email may map to multiple tenants and multiple roles (both handled —
  see the two-clinics and dr.chen cases).
- Real authentication (passwords/MFA/sessions) is out of scope. The handoff
  token proves *tenant resolution*, not identity; login forms are rendered,
  non-functional, and live on tenant origins on purpose.
- The directory's seed file stands in for a push-on-CRUD sync feed from
  tenants; the shared SMTP catcher stands in for a transactional email
  provider.
- Rate limiting and used-token state are in-memory (per-process) — Redis with
  TTLs in a real deployment.
- Each tenant's `/patients` roster is unauthenticated **on purpose**, as a
  labeled demo seam: it lets a reviewer verify the isolation claim in two
  clicks. In the real product it sits behind staff authentication.

## Bonus: the fleet drift problem

The unmentioned problem this architecture creates: with N fully isolated
deployments, every schema change is N separate migrations, and nothing forces
them to happen together. Two tenants a version apart is silent until an app
deploy assumes a column one database doesn't have. "The code bases are
identical (we are told)" — the parenthetical is the problem statement: drift
is the operational tax of the single-tenant model, and it grows linearly with
sales.

`ops/fleet_migrate.py` is the solution: numbered SQL migrations applied
per-tenant with a `schema_migrations` ledger, one transaction per migration
per tenant (a failure stops that tenant at its last good version — never
half-applied), with a drift report. It reaches each database via
`docker compose exec` because the tenant DBs publish no ports and live on
private networks — the same per-deployment access constraint the real
MSP-hosted fleet would impose.

```bash
make fleet-status                              # all tenants at 0000
python3 ops/fleet_migrate.py apply --tenant riverside   # canary
make fleet-status                              # DRIFT: riverside ahead (exit 2)
make fleet-migrate                             # converge; idempotent
```

The canary flag doubles as the real-world rollout pattern: migrate one
friendly tenant, watch it, then converge the fleet. This tool is also
deliberately Phase-1 groundwork for the migration plan below — you cannot
consolidate N databases you can't first prove are at the same version.

## Migration plan to multi-tenant

The strategy in one sentence: **change one isolation mechanism at a time,
per-tenant, with the old deployment kept warm until the new one has proven
itself — and never let a phase weaken the guarantee the previous phase
provided.** Each phase below states the guarantee it preserves and its
rollback.

**Phase 0 — control plane extraction (this exercise).** Discovery, routing,
and fleet schema tooling move to shared infrastructure; PHI, credentials, and
authentication do not. *Guarantee:* tenant data and auth remain fully
isolated; the new shared surface stores only peppered hashes. *Rollback:*
turn off the portal — tenant subdomains still work exactly as before. This
phase is deliberately additive.

**Phase 1 — fleet convergence.** Before consolidating anything, make the N
deployments provably identical: one artifact version fleet-wide, per-tenant
config (not code) as the only difference, schema versions enforced by the
migration runner (`ops/fleet_migrate.py`) with drift as a CI failure.
*Guarantee:* unchanged — this phase touches process, not topology.
*Rollback:* per-tenant version pinning. You cannot merge N databases you
can't first prove are at the same schema version; this is why the bonus tool
exists.

**Phase 2 — shared cluster, schema-per-tenant.** Move tenants onto a shared
Postgres cluster, one schema per tenant, one *database role* per tenant whose
grants reach only its own schema. The app tier can consolidate too — tenant
resolved at the edge (Host header, as here), connection taken from that
tenant's pool as that tenant's role. *Guarantee:* isolation moves from
network topology to role grants — still enforced by the database, still not
by WHERE clauses; an app-tier bug hits a wall of `permission denied`.
*Migration mechanics, per tenant:* logical-replicate the dedicated instance
into the shared cluster's schema → verify (row counts + checksums) → cut
reads over → dual-write window → cut writes → keep the dedicated instance
warm for 30 days. *Rollback:* reverse the replication direction and repoint
DNS — per-tenant, not fleet-wide, and rehearsed on a friendly tenant first
(the same canary pattern as `--tenant`). Sequencing: smallest, friendliest
customers first; enterprise and compliance-sensitive accounts last — or
never (see Phase 3).

**Phase 3 — pooled tables + RLS for the tail, dedicated schemas for the
head.** Full row-level-security pooling only ever pays for itself on the
long tail of small practices; the largest / most compliance-sensitive
accounts stay schema-per-tenant indefinitely, and that's a feature ("your
data lives in its own schema" is a sales answer, not a compromise). The
honest risk statement: **a bad RLS policy is a breach, not a bug.** If this
phase happens at all, the entry criteria are: tenant id set by connection
middleware (session GUC), never by query authors; RLS policies on every
table with no bypass roles in the app path; and an automated cross-tenant
leak test in CI — connect as tenant A, run the full API surface, assert zero
rows of tenant B, for every migration. *Rollback:* a pooled tenant can be
extracted back to a schema by filtered dump — kept tested, not theoretical.

**What never changes, in any phase:** patients and providers authenticate
only on tenant origins; the directory stores hashes and routing, never PHI
or credentials; and the isolation property currently proven by
`make verify` must have an equivalent executable proof in each new topology
before any tenant migrates onto it. A central identity provider (one
Brydon-wide patient login, SSO into tenants) is a candidate *after* Phase 2
— it was considered for this exercise and rejected as a premature shared
credential surface; at fleet scale, done properly with passkeys and
per-tenant SSO federation, it becomes worth its compliance cost.

## What I'd do differently with more time

- **Real auth on tenant origins** — per-tenant OIDC with passkeys/WebAuthn
  and MFA. The current forms are inert by design, but the handoff-token
  contract was shaped so a real IdP slots in behind the same landing pages.
- **Asymmetric handoff signing.** The directory currently shares a symmetric
  key with tenant apps; it should sign with a private key tenants verify
  against a public one, so a compromised tenant can't mint handoffs.
- **Real state stores.** The directory index in a small encrypted Postgres
  with an audited sync API (push-on-CRUD from tenants, mTLS); used-token IDs
  and rate counters in Redis with TTLs instead of per-process memory.
- **An automated test suite.** The flows verified by hand and in
  `scripts/verify_isolation.sh` — uniform hit/miss bodies *and timing*,
  single-use enforcement, cross-tenant handoff rejection, the two-clinics
  and dual-role emails — belong in pytest against the compose stack, in CI.
- **Operational hardening.** TLS everywhere (Caddy makes this nearly free),
  secrets from a manager instead of compose env, structured audit logs on
  every directory lookup and redeem (who asked, hash prefix, outcome), and
  real deliverability (DKIM/SPF/DMARC) for portal mail — patients must be
  able to trust these emails, or the whole discovery channel trains them to
  click lookalikes.
- **A tighter demo of the marketing flow** — the provider form posts
  cross-origin from the static site; a real deployment would proxy it
  same-origin and add CSRF protection.
