"""Generate per-tenant seed SQL + the directory email index seed.

Run once (or via `make seed`) to regenerate seeds/init/*.sql and
seeds/directory_seed.json. Data is FHIR R4-shaped (Patient resources)
to mirror what a real pediatric therapy EHR would hold — see README.

Deliberate edge case: guardian.two-clinics@example.com exists in BOTH
riverside and lakeside (a parent with children at two practices). The
portal flow must handle a multi-tenant hit gracefully.
"""

import json
import pathlib

TENANTS = {
    "riverside": ("Riverside Pediatric Therapy", [
        ("Ava", "Nguyen", "2018-03-14", "ava.parent@example.com"),
        ("Liam", "Okafor", "2016-11-02", "okafor.family@example.com"),
        ("Mia", "Two-Clinics", "2019-06-21", "guardian.two-clinics@example.com"),
    ]),
    "lakeside": ("Lakeside Pediatrics", [
        ("Noah", "Petrov", "2017-01-30", "petrov.home@example.com"),
        ("Zoe", "Two-Clinics", "2021-09-09", "guardian.two-clinics@example.com"),
        ("Ethan", "Silva", "2015-05-05", "silva.parents@example.com"),
    ]),
    "maple": ("Maple Grove Therapy", [
        ("Olivia", "Haddad", "2018-12-12", "haddad.family@example.com"),
        ("Lucas", "Kim", "2020-02-02", "kim.household@example.com"),
    ]),
    "harborview": ("Harborview Kids", [
        ("Amelia", "Rossi", "2016-07-19", "rossi.parent@example.com"),
        ("Mason", "Diallo", "2019-04-08", "diallo.family@example.com"),
    ]),
    "sunrise": ("Sunrise Speech & OT", [
        ("Harper", "Novak", "2017-10-25", "novak.home@example.com"),
        ("Elijah", "Tanaka", "2021-01-15", "tanaka.family@example.com"),
    ]),
}

HERE = pathlib.Path(__file__).parent
INIT = HERE / "init"
INIT.mkdir(exist_ok=True)


def fhir_patient(given, family, dob, email):
    return {
        "resourceType": "Patient",
        "name": [{"given": [given], "family": family}],
        "birthDate": dob,
        "contact": [{  # guardian contact — pediatric context
            "relationship": [{"text": "guardian"}],
            "telecom": [{"system": "email", "value": email}],
        }],
    }


def main():
    directory_seed = {}
    for tenant_id, (name, patients) in TENANTS.items():
        stmts = [
            "CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);",
            "CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);",
        ]
        emails = []
        for given, family, dob, email in patients:
            resource = json.dumps(fhir_patient(given, family, dob, email)).replace("'", "''")
            stmts.append(f"INSERT INTO patients (resource) VALUES ('{resource}');")
            if email not in emails:
                emails.append(email)
        for email in emails:
            stmts.append(f"INSERT INTO portal_users (email) VALUES ('{email}');")
        (INIT / f"{tenant_id}.sql").write_text("\n".join(stmts) + "\n")
        directory_seed[tenant_id] = emails
        print(f"wrote init/{tenant_id}.sql ({len(patients)} patients)")

    (HERE / "directory_seed.json").write_text(json.dumps(directory_seed, indent=2))
    print("wrote directory_seed.json")
    print("NOTE: guardian.two-clinics@example.com is in riverside AND lakeside (by design).")


if __name__ == "__main__":
    main()
