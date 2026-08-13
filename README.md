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

## Architecture

```
                        ┌─ www.*  ──────► marketing (static)
 browser ──► Caddy ─────┼─ portal.* ────► directory (control plane) ──► Mailpit
 (*.brydon.localhost)   └─ {tenant}.* ──► app-{tenant} ──► db-{tenant}
                                            × 5, fully isolated stacks
```

Five tenants, each a genuinely isolated deployment: its own app container and
its own Postgres *instance* with its own credentials. Isolation is enforced by
topology, not by WHERE clauses — no code path in any tenant app can reach
another tenant's database. Caddy stands in for DNS/edge routing. The only
shared services are the proxy, Mailpit (the email channel), and the directory.

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
     statement: a bad RLS policy is a breach, not a bug. A central IdP
     (one Brydon-wide patient login, SSO into tenants) is a candidate
     later phase — considered for this exercise and deferred as a major
     shared-infrastructure commitment. -->

## What I'd do differently with more time

<!-- TODO -->
