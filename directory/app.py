"""Tenant Directory service — the control plane.

This is the ONLY shared component that knows about all tenants, and it is
deliberately minimal: it maps hash(email) -> (tenant_id, audience) and
nothing else. No names, no PHI, no credentials. See README "The tenant
directory".

The one rule everything below follows: THE SHARED LAYER RESOLVES *WHERE*;
ONLY THE TENANT'S OWN ORIGIN EVER SEES PROOF OF *WHO*. No password, and no
authentication decision, ever passes through this service.

One lookup mechanism, two disclosure postures (see README for the full
reasoning):

  * Patients (portal.brydon.localhost): uniform response for hit and miss;
    the email->clinic mapping is health information, so it is only ever
    revealed inside an inbox the requester already controls. The emailed
    link routes to the clinic's LOGIN PAGE — it does not authenticate.
  * Providers (marketing "Log In"): direct redirect to the clinic's staff
    login on a hit. Staff emails are semi-public and mostly clinic-domain,
    so home-realm-discovery-style disclosure is an accepted trade-off,
    blunted by rate limiting.

Anti-enumeration posture for the patient flow:
  - Identical response body for hit and miss.
  - Email sending happens in a background task, so response TIMING is
    uniform by construction — the request never waits on SMTP.
  - Rate-limited responses are the same uniform page (the limiter silently
    drops the email send; it never emits a distinguishable error).
"""

import hashlib
import json
import os
import secrets
import smtplib
import time
from email.message import EmailMessage

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SECRET_KEY = os.environ["SECRET_KEY"]
PEPPER = os.environ["PEPPER"]
# Shared secret gating the service-to-service mint API. Stands in for mTLS:
# the directory mints links only for callers that present it.
INTERNAL_AUTH = os.environ["INTERNAL_AUTH"]
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "brydon.localhost:8080")
SEED_FILE = os.environ.get("SEED_FILE", "/seeds/directory_seed.json")
SMTP_HOST = os.environ.get("SMTP_HOST", "mail")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))

# Token lifetimes. Discovery links were requested seconds ago, so they are
# short-lived and single-use. Reminder links get opened days after the
# appointment email went out, so they are long-lived and multi-use — safe
# because redeeming one only routes to a login page, it authenticates no one.
DISCOVERY_MAX_AGE = 15 * 60
REMINDER_MAX_AGE = 7 * 24 * 3600
RATE_LIMIT_MAX = 10         # lookups ...
RATE_LIMIT_WINDOW = 60.0    # ... per key (IP and email hash) per window

app = FastAPI(title="Brydon Tenant Directory")

# Separate salts = separate token namespaces: a portal link can never be
# replayed as a tenant handoff or vice versa.
_links = URLSafeTimedSerializer(SECRET_KEY, salt="portal-link")
_handoff = URLSafeTimedSerializer(SECRET_KEY, salt="tenant-handoff")

# In-memory stores for the simulation. In the real product the index is a
# small, encrypted, audited datastore synced from each tenant (push on user
# CRUD, hashed on ingest); used-token IDs and rate counters live in Redis
# with TTLs.
_index: dict[str, list[dict]] = {}   # email_hash -> [{"t": id, "aud": ...}]
_tenant_names: dict[str, str] = {}   # tenant_id -> display name
_used_jtis: set[str] = set()         # single-use enforcement, discovery links
_rate: dict[str, list[float]] = {}   # "ip:.."/"em:.." key -> recent timestamps


def email_hash(email: str) -> str:
    normalized = email.strip().lower()
    return hashlib.sha256((PEPPER + normalized).encode()).hexdigest()


@app.on_event("startup")
def load_seed():
    with open(SEED_FILE) as f:
        seed = json.load(f)
    for tenant_id, t in seed["tenants"].items():
        _tenant_names[tenant_id] = t["name"]
        for e in t["patients"]:
            _index.setdefault(email_hash(e), []).append({"t": tenant_id, "aud": "patient"})
        for e in t["providers"]:
            _index.setdefault(email_hash(e), []).append({"t": tenant_id, "aud": "provider"})


def _rate_limited(request: Request, email: str | None = None) -> bool:
    """Throttle on two independent keys: source IP and the peppered email
    hash. IP alone folds against distributed probing — one target address
    fanned across many hosts — so the email-hash key catches exactly that
    (the pepper keeps it non-reversible). A hit on EITHER key limits the
    request; both keys are always recorded so neither can be starved."""
    # Caddy sets X-Forwarded-For; direct hits fall back to the socket peer.
    ip = (request.headers.get("x-forwarded-for") or request.client.host).split(",")[0].strip()
    now = time.monotonic()
    keys = [f"ip:{ip}"]
    if email:
        keys.append(f"em:{email_hash(email)}")
    limited = False
    for key in keys:
        recent = [ts for ts in _rate.get(key, []) if now - ts < RATE_LIMIT_WINDOW]
        recent.append(now)
        _rate[key] = recent
        if len(recent) > RATE_LIMIT_MAX:
            limited = True
    return limited


# ---------------------------------------------------------------- patient UI

@app.get("/", response_class=HTMLResponse)
def portal_home():
    return f"""
    <html><body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
      <h1>Brydon Health Patient Portal</h1>
      <p>Enter your email and we'll send you a secure link to your clinic's
         sign-in page.</p>
      <form method="post" action="/lookup">
        <input type="email" name="email" required placeholder="you@example.com"
               style="width: 100%; padding: .5rem;">
        <input type="hidden" name="audience" value="patient">
        <button style="margin-top: .75rem; padding: .5rem 1rem;">Email me a sign-in link</button>
      </form>
    </body></html>
    """


# ----------------------------------------------------------------- discovery

@app.post("/lookup")
def lookup(
    request: Request,
    background: BackgroundTasks,
    email: str = Form(...),
    audience: str = Form("patient"),
):
    """Discovery endpoint — both audiences, one index, two postures."""
    limited = _rate_limited(request, email)

    if audience == "provider":
        if not limited:
            hits = [e for e in _index.get(email_hash(email), []) if e["aud"] == "provider"]
            if hits:
                # Accepted disclosure (see README): staff emails are
                # semi-public, and only an exact registered address hits.
                return _provider_redirect(hits)
        # Unrecognized (or throttled) provider lookup degrades to the
        # patient posture: uniform page, email if the address is known.

    if not limited:
        background.add_task(_deliver_if_known, email)
    return HTMLResponse(_uniform_response())


def _provider_redirect(hits: list[dict]):
    if len(hits) == 1:
        t = hits[0]["t"]
        token = _handoff.dumps({"t": t, "aud": "provider"})
        return RedirectResponse(
            url=f"http://{t}.{BASE_DOMAIN}/login?handoff={token}", status_code=303
        )
    # Staff at multiple practices: they proved nothing yet, but provider
    # disclosure is the accepted trade-off, so a chooser is acceptable here.
    items = ""
    for e in hits:
        token = _handoff.dumps({"t": e["t"], "aud": "provider"})
        items += (
            f'<li><a href="http://{e["t"]}.{BASE_DOMAIN}/login?handoff={token}">'
            f"{_tenant_names[e['t']]}</a></li>"
        )
    return HTMLResponse(f"""
    <html><body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
      <h2>Choose your practice</h2>
      <ul>{items}</ul>
    </body></html>
    """)


def _deliver_if_known(email: str) -> None:
    entries = _index.get(email_hash(email), [])
    if not entries:
        return  # miss: silence — the requester already got the uniform page.
    _send_signin_email(email, entries)


def _send_signin_email(to_email: str, entries: list[dict]) -> None:
    """One email, one link per (tenant, role). A guardian with children at
    two practices gets both links; a therapist who is also a parent gets a
    staff link and a patient link, labeled."""
    links = []
    for e in entries:
        token = _links.dumps(
            {"t": e["t"], "aud": e["aud"], "p": "discovery", "jti": secrets.token_urlsafe(9)}
        )
        label = _tenant_names.get(e["t"], e["t"])
        if e["aud"] == "provider":
            label += " (staff sign-in)"
        links.append((label, f"http://portal.{BASE_DOMAIN}/t/{token}"))

    intro = (
        "You have more than one account with practices we work with. "
        "Choose the one you need:"
        if len(links) > 1
        else "Click below to go to your clinic's sign-in page."
    )
    msg = EmailMessage()
    msg["From"] = f"Brydon Health Portal <no-reply@{BASE_DOMAIN.split(':')[0]}>"
    msg["To"] = to_email
    msg["Subject"] = "Your sign-in link"
    msg.set_content("\n".join([intro, ""] + [f"{name}: {url}" for name, url in links]))
    items = "".join(
        f'<p><a href="{url}" style="padding:.5rem 1rem;background:#1a5fb4;'
        f'color:white;text-decoration:none;">{name}</a></p>'
        for name, url in links
    )
    msg.add_alternative(
        f"""<html><body style="font-family: sans-serif;">
        <p>{intro}</p>{items}
        <p><small>These links expire in 15 minutes and work once. They take
        you to your clinic's sign-in page — you'll sign in there as usual.
        If you didn't request this, you can ignore it.</small></p>
        </body></html>""",
        subtype="html",
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.send_message(msg)


def _uniform_response() -> str:
    # Identical for every input, by construction.
    return """
    <html><body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
      <h2>Check your email</h2>
      <p>If we have an account matching that address, a secure sign-in
         link is on its way. It expires in 15 minutes.</p>
    </body></html>
    """


# -------------------------------------------------------------------- redeem

@app.get("/t/{token}")
def redeem(token: str):
    """Redeem a portal link -> redirect to the correct tenant's login page.

    The tenant comes from the signed token and nowhere else. Policy depends
    on the token's purpose:
      discovery: <=15 min old AND never used before.
      reminder:  <=7 days old, multi-use (patients reopen reminder emails;
                 the link only routes to a login page, so replay yields no
                 access and no new disclosure beyond the email itself).

    On success we mint a FRESH 60-second handoff token (different salt) so
    the tenant app can verify the redirect came from the directory — the
    emailed token itself never reaches the tenant.
    """
    try:
        data = _links.loads(token, max_age=REMINDER_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return _dead_link_response()

    if data.get("p") == "discovery":
        try:
            _links.loads(token, max_age=DISCOVERY_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return _dead_link_response()
        if data["jti"] in _used_jtis:
            return _dead_link_response()
        _used_jtis.add(data["jti"])

    handoff = _handoff.dumps({"t": data["t"], "aud": data["aud"]})
    dest = "/login" if data["aud"] == "provider" else "/portal/landing"
    return RedirectResponse(url=f"http://{data['t']}.{BASE_DOMAIN}{dest}?handoff={handoff}")


def _dead_link_response() -> HTMLResponse:
    # One page for expired / tampered / already-used: a dead link should
    # not disclose WHY it is dead.
    return HTMLResponse(
        """
        <html><body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
          <h2>That link is no longer valid</h2>
          <p>Sign-in links from the portal expire and can only be used once.
             <a href="/">Request a new one</a>.</p>
        </body></html>
        """,
        status_code=410,
    )


# ------------------------------------------------------------- internal API

@app.post("/internal/deep-link")
def mint_deep_link(payload: dict, request: Request):
    """Mint a pre-signed reminder deep link for a tenant's outbound email
    (automated reminders, clinic campaigns). The tenant already knows who
    its own patients are, so no discovery round-trip is needed — see README.

    Two layers guard this: Caddy 404s /internal/* at the public edge, and a
    shared-secret X-Internal-Auth header authenticates the caller on the
    service network — so a foothold on the network still can't mint links
    for arbitrary tenants. In the real product the header would be mTLS.
    """
    if not secrets.compare_digest(request.headers.get("x-internal-auth", ""), INTERNAL_AUTH):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    tenant_id = payload["tenant_id"]
    if tenant_id not in _tenant_names:
        return JSONResponse({"error": "unknown tenant"}, status_code=400)
    token = _links.dumps({"t": tenant_id, "aud": "patient", "p": "reminder"})
    return {"url": f"http://portal.{BASE_DOMAIN}/t/{token}"}


@app.get("/healthz")
def healthz():
    return {"ok": True, "known_hashes": len(_index)}
