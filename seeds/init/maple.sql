CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);
CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
CREATE TABLE staff (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Olivia"], "family": "Haddad"}], "birthDate": "2018-12-12", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "haddad.family@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Lucas"], "family": "Kim"}], "birthDate": "2020-02-02", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "kim.household@example.com"}]}]}');
INSERT INTO portal_users (email) VALUES ('haddad.family@example.com');
INSERT INTO portal_users (email) VALUES ('kim.household@example.com');
INSERT INTO staff (email) VALUES ('hello@maplegrovetherapy.com');
