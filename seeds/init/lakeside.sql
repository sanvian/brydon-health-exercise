CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);
CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Noah"], "family": "Petrov"}], "birthDate": "2017-01-30", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "petrov.home@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Zoe"], "family": "Two-Clinics"}], "birthDate": "2021-09-09", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "guardian.two-clinics@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Ethan"], "family": "Silva"}], "birthDate": "2015-05-05", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "silva.parents@example.com"}]}]}');
INSERT INTO portal_users (email) VALUES ('petrov.home@example.com');
INSERT INTO portal_users (email) VALUES ('guardian.two-clinics@example.com');
INSERT INTO portal_users (email) VALUES ('silva.parents@example.com');
