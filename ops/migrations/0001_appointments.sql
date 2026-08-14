-- Appointments: the reminder flow's natural data model.
CREATE TABLE appointments (
    id serial PRIMARY KEY,
    patient_id integer NOT NULL REFERENCES patients (id),
    starts_at timestamptz NOT NULL,
    kind text NOT NULL DEFAULT 'therapy'
);
