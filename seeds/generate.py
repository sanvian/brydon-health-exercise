"""Generate per-tenant seed SQL + the directory email index seed.

Run once (or via `make seed`) to regenerate seeds/init/*.sql and
seeds/directory_seed.json. Data is FHIR R4-shaped (Patient resources)
to mirror what a real pediatric therapy EHR would hold — see README.

Deliberate edge cases:
  * guardian.two-clinics@example.com is a guardian in BOTH riverside and
    lakeside (a parent with children at two practices). The portal flow
    must handle a multi-tenant hit gracefully.
  * dr.chen@riversidepeds.com is STAFF at riverside and a PATIENT guardian
    at lakeside — one email, two roles, two tenants. This is why the
    directory stores an `audience` per entry instead of inferring it.
  * lakesidepedsoffice@gmail.com is a staff account on a consumer domain —
    small practices do this, which is why audience can't be derived from
    the email's domain.
"""

import json
import pathlib

TENANTS = {
    "riverside": {
        "name": "Riverside Pediatric Therapy",
        "patients": [
            ("Ava", "Nguyen", "2018-03-14", "ava.parent@example.com"),
            ("Liam", "Okafor", "2016-11-02", "okafor.family@example.com"),
            ("Mia", "Two-Clinics", "2019-06-21", "guardian.two-clinics@example.com"),
        ],
        "providers": ["frontdesk@riversidepeds.com", "dr.chen@riversidepeds.com"],
    },
    "lakeside": {
        "name": "Lakeside Pediatrics",
        "patients": [
            ("Noah", "Petrov", "2017-01-30", "petrov.home@example.com"),
            ("Zoe", "Two-Clinics", "2021-09-09", "guardian.two-clinics@example.com"),
            ("Ethan", "Silva", "2015-05-05", "silva.parents@example.com"),
            ("Theo", "Chen", "2020-08-17", "dr.chen@riversidepeds.com"),
        ],
        "providers": ["office@lakesidepediatrics.com", "lakesidepedsoffice@gmail.com"],
    },
    "maple": {
        "name": "Maple Grove Therapy",
        "patients": [
            ("Olivia", "Haddad", "2018-12-12", "haddad.family@example.com"),
            ("Lucas", "Kim", "2020-02-02", "kim.household@example.com"),
        ],
        "providers": ["hello@maplegrovetherapy.com"],
    },
    "harborview": {
        "name": "Harborview Kids",
        "patients": [
            ("Amelia", "Rossi", "2016-07-19", "rossi.parent@example.com"),
            ("Mason", "Diallo", "2019-04-08", "diallo.family@example.com"),
        ],
        "providers": ["staff@harborviewkids.com"],
    },
    "sunrise": {
        "name": "Sunrise Speech & OT",
        "patients": [
            ("Harper", "Novak", "2017-10-25", "novak.home@example.com"),
            ("Elijah", "Tanaka", "2021-01-15", "tanaka.family@example.com"),
        ],
        "providers": ["office@sunrisespeech.com"],
    },
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
    for tenant_id, t in TENANTS.items():
        stmts = [
            "CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);",
            "CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);",
            "CREATE TABLE staff (id serial PRIMARY KEY, email text UNIQUE NOT NULL);",
        ]
        guardian_emails = []
        for given, family, dob, email in t["patients"]:
            resource = json.dumps(fhir_patient(given, family, dob, email)).replace("'", "''")
            stmts.append(f"INSERT INTO patients (resource) VALUES ('{resource}');")
            if email not in guardian_emails:
                guardian_emails.append(email)
        for email in guardian_emails:
            stmts.append(f"INSERT INTO portal_users (email) VALUES ('{email}');")
        for email in t["providers"]:
            stmts.append(f"INSERT INTO staff (email) VALUES ('{email}');")
        (INIT / f"{tenant_id}.sql").write_text("\n".join(stmts) + "\n")
        directory_seed[tenant_id] = {
            "name": t["name"],
            "patients": guardian_emails,
            "providers": t["providers"],
        }
        print(f"wrote init/{tenant_id}.sql ({len(t['patients'])} patients, {len(t['providers'])} staff)")

    (HERE / "directory_seed.json").write_text(
        json.dumps({"tenants": directory_seed}, indent=2) + "\n"
    )
    print("wrote directory_seed.json")
    print("NOTE: guardian.two-clinics@example.com is a guardian in riverside AND lakeside.")
    print("NOTE: dr.chen@riversidepeds.com is staff at riverside AND a guardian at lakeside.")


if __name__ == "__main__":
    main()
