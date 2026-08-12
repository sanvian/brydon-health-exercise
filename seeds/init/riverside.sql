CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);
CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Ava"], "family": "Nguyen"}], "birthDate": "2018-03-14", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "ava.parent@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Liam"], "family": "Okafor"}], "birthDate": "2016-11-02", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "okafor.family@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Mia"], "family": "Two-Clinics"}], "birthDate": "2019-06-21", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "guardian.two-clinics@example.com"}]}]}');
INSERT INTO portal_users (email) VALUES ('ava.parent@example.com');
INSERT INTO portal_users (email) VALUES ('okafor.family@example.com');
INSERT INTO portal_users (email) VALUES ('guardian.two-clinics@example.com');
