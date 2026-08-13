CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);
CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
CREATE TABLE staff (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Amelia"], "family": "Rossi"}], "birthDate": "2016-07-19", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "rossi.parent@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Mason"], "family": "Diallo"}], "birthDate": "2019-04-08", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "diallo.family@example.com"}]}]}');
INSERT INTO portal_users (email) VALUES ('rossi.parent@example.com');
INSERT INTO portal_users (email) VALUES ('diallo.family@example.com');
INSERT INTO staff (email) VALUES ('staff@harborviewkids.com');
