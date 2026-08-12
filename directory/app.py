"""Tenant Directory service — the control plane.

This is the ONLY shared component that knows about all tenants, and it is
deliberately minimal: it maps hash(email) -> tenant_id and nothing else.
No names, no PHI, no per-tenant data. See README "Data minimization".

It serves two audiences with one mechanism:
  * portal.brydon.localhost  -> patient discovery (magic link via email)
  * marketing "Log In"       -> provider discovery (same lookup, different UX)

Anti-enumeration invariant (the whole point):
  Every response to a discovery request is IDENTICAL whether or not the
  email exists in any tenant. Existence is only ever revealed inside the
  email channel, which the requester must already control.

Implementation status: scaffold. The endpoints below define the contract;
the interesting parts are TODO seams to be built commit-by-commit
(see COMMIT_PLAN.md).
"""

import hashlib
import json
import os

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

SECRET_KEY = os.environ["SECRET_KEY"]
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "brydon.localhost:8080")
SEED_FILE = os.environ.get("SEED_FILE", "/seeds/directory_seed.json")
PEPPER = "dev-pepper"  # TODO(hardening): env-provided, rotated secret

app = FastAPI(title="Brydon Tenant Directory")

# In-memory store for the simulation. In the real product this is a small,
# encrypted, audited datastore synced from each tenant (push on user CRUD).
_index: dict[str, list[str]] = {}  # email_hash -> [tenant_id, ...]


def email_hash(email: str) -> str:
    normalized = email.strip().lower()
    return hashlib.sha256((PEPPER + normalized).encode()).hexdigest()


@app.on_event("startup")
def load_seed():
    with open(SEED_FILE) as f:
        seed = json.load(f)
    for tenant_id, emails in seed.items():
        for e in emails:
            _index.setdefault(email_hash(e), []).append(tenant_id)


@app.get("/", response_class=HTMLResponse)
def portal_home():
    return f"""
    <html><body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
      <h1>Brydon Health Patient Portal</h1>
      <p>Enter your email and we'll send you a secure sign-in link.</p>
      <form method="post" action="/lookup">
        <input type="email" name="email" required placeholder="you@example.com"
               style="width: 100%; padding: .5rem;">
        <input type="hidden" name="audience" value="patient">
        <button style="margin-top: .75rem; padding: .5rem 1rem;">Email me a sign-in link</button>
      </form>
    </body></html>
    """


@app.post("/lookup", response_class=HTMLResponse)
def lookup(email: str = Form(...), audience: str = Form("patient")):
    """Discovery endpoint. MUST be indistinguishable for hit vs. miss.

    TODO(core, in order — see COMMIT_PLAN.md):
      1. Look up email_hash(email) in _index.
      2. On hit: issue a short-lived signed token {tenants, audience, exp}
         (itsdangerous.URLSafeTimedSerializer) and email a magic link
         per tenant via SMTP -> Mailpit. Multi-tenant hits (parent with
         children at two practices) list BOTH links in one email.
      3. On miss: do nothing — but burn comparable time so response
         timing doesn't leak existence (constant-time posture).
      4. Rate-limit by IP + email to blunt bulk enumeration probing.
    """
    _ = email_hash(email)  # placeholder so the seam is visible
    return _uniform_response()


def _uniform_response() -> str:
    # Identical for every input, by construction.
    return """
    <html><body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
      <h2>Check your email</h2>
      <p>If we have an account matching that address, a secure sign-in
         link is on its way. It expires in 15 minutes.</p>
    </body></html>
    """


@app.get("/t/{token}")
def redeem(token: str):
    """Redeem a magic-link token -> redirect into the correct tenant.

    TODO(core): verify signature + expiry + single-use, then redirect to
    http://{tenant}.{BASE_DOMAIN}/portal/landing?handoff=<short-lived token>
    so the tenant app can establish its own session. Never trust the
    tenant from anything except the signed token.
    """
    return RedirectResponse(url=f"http://portal.{BASE_DOMAIN}/")  # placeholder


@app.get("/healthz")
def healthz():
    return {"ok": True, "known_hashes": len(_index)}
