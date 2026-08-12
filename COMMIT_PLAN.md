# Commit plan

They said a technical leader will read the history, so the history is a
second README: small increments, each message stating *what and why*.
Delete this file before submission (or keep it — arguably it shows process).

1. `chore: scaffold — compose topology, proxy routing, service skeletons`
   Structure + docker-compose + Caddyfile + stub apps. Nothing works yet
   beyond containers starting.
2. `feat: five isolated tenant stacks with FHIR-shaped seed data`
   Per-tenant Postgres instances + seed generator. Note the deliberate
   two-clinics guardian edge case in the message.
3. `feat: subdomain routing — simulated single-tenant baseline complete`
   Tenant apps serving their own data via Host-header routing. This is
   deliverable #1 done; say so.
4. `test: prove isolation (per-tenant creds, no cross-tenant path)`
   Small script/curl checks showing riverside cannot see lakeside.
5. `feat: tenant directory — peppered email-hash index (control plane)`
   The minimal shared state. Commit message carries the data-minimization
   rationale — this is the compliance-critical decision.
6. `feat: portal discovery with uniform hit/miss response`
   The anti-enumeration invariant lands here. State it in the message.
7. `feat: magic-link issue + redeem — signed, 15-min, single-use`
   itsdangerous tokens, SMTP → Mailpit, redirect to tenant landing with
   handoff token. Deliverable #2 done.
8. `feat: multi-tenant email handled — one email, both org links`
   The parent-with-two-practices case. Small commit, big signal.
9. `feat: reminder deep links — pre-signed, skip discovery entirely`
   Covers the exercise's automated-reminders hint.
10. `feat: marketing Log In via shared discovery (provider audience)`
    Deliverable #3, reusing the same mechanism — the commit message should
    make the "one mechanism, two problems" point explicit.
11. `feat: hardening — rate limiting, timing uniformity, token replay`
12. `feat(bonus): fleet migration runner + schema-version drift report`
13. `docs: README — architecture, tradeoffs, assumptions`
14. `docs: migration plan to multi-tenant (phases, rollback, risks)`
15. `docs: CEO one-pager` (docs/ceo-onepager.md → export)
16. `chore: final pass — run instructions verified from clean checkout`

Rules of the road:
- Commit as YOU, from your machine, in this order — don't squash.
- Before commit 16, actually do a clean `git clone` + `make up` on a
  fresh directory; "how to run it" failing is the worst possible bug.
