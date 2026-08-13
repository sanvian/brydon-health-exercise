CREATE TABLE patients (id serial PRIMARY KEY, resource jsonb NOT NULL);
CREATE TABLE portal_users (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
CREATE TABLE staff (id serial PRIMARY KEY, email text UNIQUE NOT NULL);
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Harper"], "family": "Novak"}], "birthDate": "2017-10-25", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "novak.home@example.com"}]}]}');
INSERT INTO patients (resource) VALUES ('{"resourceType": "Patient", "name": [{"given": ["Elijah"], "family": "Tanaka"}], "birthDate": "2021-01-15", "contact": [{"relationship": [{"text": "guardian"}], "telecom": [{"system": "email", "value": "tanaka.family@example.com"}]}]}');
INSERT INTO portal_users (email) VALUES ('novak.home@example.com');
INSERT INTO portal_users (email) VALUES ('tanaka.family@example.com');
INSERT INTO staff (email) VALUES ('office@sunrisespeech.com');
