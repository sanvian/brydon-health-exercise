"""Simulated single-tenant EHR application.

One image, five instances. Each instance knows exactly one tenant
(TENANT_ID / TENANT_NAME) and can reach exactly one database
(DATABASE_URL). There is deliberately no code path that could touch
another tenant's data — network topology and credentials enforce
isolation, not application logic. That property is what the real
product's compliance story rests on, and what any multi-tenant
migration must preserve.

Authentication is deliberately SIMULATED (see README "Assumptions"):
the exercise is about tenant discovery, not identity. What matters
architecturally is that the login form lives HERE, on the tenant's own
origin — credentials never touch the shared portal, and origin-bound
auth (passkeys/WebAuthn, per-tenant MFA) stays possible.
"""

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage

import psycopg
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

TENANT_ID = os.environ["TENANT_ID"]
TENANT_NAME = os.environ["TENANT_NAME"]
DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
DIRECTORY_URL = os.environ.get("DIRECTORY_URL", "http://directory:8000")
SMTP_HOST = os.environ.get("SMTP_HOST", "mail")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))

# Must match the directory's handoff serializer. In the real product this
# would be asymmetric: directory signs, tenants hold only the public key.
_handoff = URLSafeTimedSerializer(SECRET_KEY, salt="tenant-handoff")
HANDOFF_MAX_AGE = 60

app = FastAPI(title=f"EHR — {TENANT_NAME}")


def db():
    return psycopg.connect(DATABASE_URL)


def verify_handoff(token: str | None, audience: str) -> bool:
    """True iff the directory minted this handoff, for THIS tenant and this
    audience, within the last minute. Proves routing provenance — not
    identity; the visitor still has to log in below."""
    if not token:
        return False
    try:
        data = _handoff.loads(token, max_age=HANDOFF_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("t") == TENANT_ID and data.get("aud") == audience


def _page(body: str) -> str:
    return f"""
    <html><body style="font-family: sans-serif; max-width: 640px; margin: 3rem auto;">
      {body}
      <hr><small>Simulated single-tenant EHR instance — isolated app + isolated database.</small>
    </body></html>
    """


def _login_form(role: str) -> str:
    # Simulated: renders the form, accepts nothing. Real credentials + MFA
    # are out of scope; the point is WHERE this form lives (tenant origin).
    return f"""
      <form style="border: 1px solid #ccc; padding: 1rem; max-width: 320px;">
        <b>{role} sign-in</b> <i>(simulated — auth out of scope)</i><br><br>
        <input placeholder="username" style="width: 100%; padding: .4rem;"><br><br>
        <input placeholder="password" type="password" style="width: 100%; padding: .4rem;"><br><br>
        <button type="button" disabled>Sign in</button>
      </form>
    """


@app.get("/", response_class=HTMLResponse)
def home():
    with db() as conn:
        n = conn.execute("SELECT count(*) FROM patients").fetchone()[0]
    return _page(f"""
      <h1>{TENANT_NAME}</h1>
      <p>Tenant: <code>{TENANT_ID}</code> &middot; Patients on file: <b>{n}</b></p>
      <p><a href="/login">Staff sign-in</a> &middot; <a href="/portal/landing">Patient portal</a></p>
      <p style="background:#fff8e1;padding:.5rem;"><small><b>Demo seam:</b>
         <a href="/patients">patient roster</a> — the isolation proof (same
         route, different subdomain, different children). In the real product
         this sits behind staff authentication, which is out of scope here.</small></p>
    """)


@app.get("/patients", response_class=HTMLResponse)
def patients():
    """Demo seam: unauthenticated on purpose, so a reviewer can verify the
    isolation claim in two clicks (riverside/patients vs lakeside/patients).
    In the real product this is staff-authenticated EHR data."""
    with db() as conn:
        rows = conn.execute(
            "SELECT resource FROM patients ORDER BY id"
        ).fetchall()
    items = ""
    for (resource,) in rows:
        r = resource if isinstance(resource, dict) else json.loads(resource)
        name = r["name"][0]
        items += f"<li>{name['given'][0]} {name['family']} — DOB {r['birthDate']}</li>"
    return _page(f"""
      <h2>{TENANT_NAME} — Patients</h2>
      <ul>{items}</ul>
      <p><a href="/">Back</a></p>
    """)


@app.get("/login", response_class=HTMLResponse)
def staff_login(handoff: str | None = None):
    """Staff sign-in page. Public — knowing a clinic's subdomain reveals
    nothing the clinic's own website doesn't. The handoff banner just shows
    provenance when the visitor arrived via the marketing Log In flow."""
    banner = (
        '<p style="background:#e8f5e9;padding:.5rem;">Routed here by the '
        "Brydon Health portal &#10003;</p>"
        if verify_handoff(handoff, "provider")
        else ""
    )
    return _page(f"<h1>{TENANT_NAME}</h1>{banner}{_login_form('Staff')}")


@app.get("/portal/landing", response_class=HTMLResponse)
def portal_landing(handoff: str | None = None):
    """The clinic's patient sign-in page — on the tenant's own origin.

    Reachable two ways, both first-class: directly (a returning patient who
    knows their clinic) or via the central portal / a reminder deep link (a
    patient who doesn't). The handoff token, when present and valid, proves
    the directory did the routing (right tenant, right audience, within
    60s) — provenance, not permission. It does NOT authenticate anyone,
    and its absence gates nothing: the sign-in form always renders.
    """
    banner = (
        '<p style="background:#e8f5e9;padding:.5rem;">Routed here by the '
        "Brydon Health portal &#10003; — sign in below to continue.</p>"
        if verify_handoff(handoff, "patient")
        else f"""<p><small>Don't know your clinic's portal address?
           <a href="http://portal.{os.environ.get('BASE_DOMAIN', 'brydon.localhost:8080')}/">
           Find it via the Brydon Health portal</a>.</small></p>"""
    )
    return _page(f"""
      <h1>Welcome to the {TENANT_NAME} patient portal</h1>
      {banner}
      {_login_form('Patient')}
    """)


@app.get("/demo/remind")
def send_reminder(email: str):
    """Simulates the tenant's reminder job: this instance already knows its
    own patients, so it asks the directory for a pre-signed deep link (no
    discovery round-trip) and emails it with the appointment details.
    """
    with db() as conn:
        known = conn.execute(
            "SELECT 1 FROM portal_users WHERE email = %s", (email,)
        ).fetchone()
    if not known:
        return JSONResponse({"error": "not a portal user of this tenant"}, status_code=404)

    req = urllib.request.Request(
        f"{DIRECTORY_URL}/internal/deep-link",
        data=json.dumps({"tenant_id": TENANT_ID}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        url = json.load(resp)["url"]

    msg = EmailMessage()
    msg["From"] = f"{TENANT_NAME} <reminders@{TENANT_ID}.example>"
    msg["To"] = email
    msg["Subject"] = f"Appointment reminder — {TENANT_NAME}"
    msg.set_content(
        "Reminder: you have a therapy appointment on Thursday at 3:00 PM.\n\n"
        f"View details in the patient portal: {url}\n"
    )
    msg.add_alternative(
        f"""<html><body style="font-family: sans-serif;">
        <p>Reminder: you have a therapy appointment on <b>Thursday at 3:00 PM</b>.</p>
        <p><a href="{url}" style="padding:.5rem 1rem;background:#1a5fb4;color:white;
           text-decoration:none;">View in patient portal</a></p>
        <p><small>This link takes you to the {TENANT_NAME} sign-in page.</small></p>
        </body></html>""",
        subtype="html",
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.send_message(msg)
    return {"sent": True, "to": email, "tenant": TENANT_ID}


@app.get("/healthz")
def healthz():
    return {"ok": True, "tenant": TENANT_ID}
