"""Simulated single-tenant EHR application.

One image, five instances. Each instance knows exactly one tenant
(TENANT_ID / TENANT_NAME) and can reach exactly one database
(DATABASE_URL). There is deliberately no code path that could touch
another tenant's data — network topology and credentials enforce
isolation, not application logic. That property is what the real
product's compliance story rests on, and what any multi-tenant
migration must preserve.
"""

import json
import os

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

TENANT_ID = os.environ["TENANT_ID"]
TENANT_NAME = os.environ["TENANT_NAME"]
DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title=f"EHR — {TENANT_NAME}")


def db():
    return psycopg.connect(DATABASE_URL)


@app.get("/", response_class=HTMLResponse)
def home():
    with db() as conn:
        n = conn.execute("SELECT count(*) FROM patients").fetchone()[0]
    return f"""
    <html><body style="font-family: sans-serif; max-width: 640px; margin: 3rem auto;">
      <h1>{TENANT_NAME}</h1>
      <p>Tenant: <code>{TENANT_ID}</code> &middot; Patients on file: <b>{n}</b></p>
      <p><a href="/patients">Patient roster</a></p>
      <hr><small>Simulated single-tenant EHR instance — isolated app + isolated database.</small>
    </body></html>
    """


@app.get("/patients", response_class=HTMLResponse)
def patients():
    with db() as conn:
        rows = conn.execute(
            "SELECT resource FROM patients ORDER BY id"
        ).fetchall()
    items = ""
    for (resource,) in rows:
        r = resource if isinstance(resource, dict) else json.loads(resource)
        name = r["name"][0]
        items += f"<li>{name['given'][0]} {name['family']} — DOB {r['birthDate']}</li>"
    return f"""
    <html><body style="font-family: sans-serif; max-width: 640px; margin: 3rem auto;">
      <h2>{TENANT_NAME} — Patients</h2>
      <ul>{items}</ul>
      <p><a href="/">Back</a></p>
    </body></html>
    """


@app.get("/portal/landing", response_class=HTMLResponse)
def portal_landing(request: Request):
    """Where a patient lands after the central portal resolves their tenant.

    TODO(portal): verify the signed handoff token from the directory service
    (query param), establish a patient session, and greet the patient by name.
    Until then this just proves the routing works end-to-end.
    """
    return f"""
    <html><body style="font-family: sans-serif; max-width: 640px; margin: 3rem auto;">
      <h1>Welcome to the {TENANT_NAME} patient portal</h1>
      <p>You were routed here by the central portal. (Token verification: TODO)</p>
    </body></html>
    """


@app.get("/healthz")
def healthz():
    return {"ok": True, "tenant": TENANT_ID}
