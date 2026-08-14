-- Reminder jobs scan by upcoming start time.
CREATE INDEX appointments_starts_at_idx ON appointments (starts_at);
