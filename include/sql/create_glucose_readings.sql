-- Glucose readings fetched from LibreLinkUp. One row per sensor reading
-- (about every 15 minutes). See docs/data-model.md.
--
-- TIMESTAMPTZ = an exact moment: converted to UTC on insert, shown in the
--               session's time zone on read (the zone itself isn't stored).
-- TIMESTAMP   = a wall-clock reading, stored as given, never converted, with no
--               idea which time zone it belongs to.
-- ingested_at = when the row was first stored (filled by Postgres); with
--               ON CONFLICT DO NOTHING it never changes. Useful for debugging.
CREATE TABLE IF NOT EXISTS glucose_readings (
    factory_timestamp  TIMESTAMPTZ  PRIMARY KEY,  -- sensor time, UTC: the upsert key
    local_timestamp    TIMESTAMP    NOT NULL,     -- phone's local time, no time zone
    value_mg_dl        REAL         NOT NULL,     -- glucose in mg/dL
    ingested_at        TIMESTAMPTZ  NOT NULL DEFAULT now()  -- when we first stored it
);