CREATE DATABASE crown_marketing
    OWNER postgres
    ENCODING 'UTF8';

CREATE ROLE crown_admin
    LOGIN
    PASSWORD 'PASSWORD_IS_IN_PGPASS'
    CREATEDB;

GRANT CONNECT, TEMPORARY ON DATABASE crown_marketing TO crown_admin;
CREATE SCHEMA IF NOT EXISTS staging;
GRANT USAGE, CREATE ON SCHEMA staging TO crown_admin;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA staging TO crown_admin;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA staging TO crown_admin;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging
  GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO crown_admin;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging
  GRANT USAGE,SELECT,UPDATE ON SEQUENCES TO crown_admin;

CREATE TABLE IF NOT EXISTS staging.raw_file (
    id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_date DATE NOT NULL,
    imported_at TIMESTAMPTZ DEFAULT now(),
    row_count INTEGER
);

CREATE TABLE IF NOT EXISTS staging.raw_row (
    id BIGSERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES staging.raw_file(id) ON DELETE CASCADE,
    row_data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.product_history (
    id           BIGSERIAL PRIMARY KEY,
    number       TEXT        NOT NULL,
    other_number TEXT,
    file_id      INTEGER     NOT NULL REFERENCES staging.raw_file (id) ON DELETE RESTRICT,
    file_date    DATE        NOT NULL,
    date_modified TIMESTAMP  NULL,
    data         JSONB       NOT NULL,
    row_hash     CHAR(64)    NOT NULL,
    is_current   BOOLEAN     NOT NULL DEFAULT TRUE
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_product_history_number_filedate
    ON staging.product_history (number, file_date DESC);

CREATE INDEX IF NOT EXISTS idx_product_history_file_id
    ON staging.product_history (file_id);

CREATE INDEX IF NOT EXISTS idx_product_history_current
    ON staging.product_history (number)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS staging.product_history_file (
    file_id         INTEGER PRIMARY KEY REFERENCES staging.raw_file (id) ON DELETE CASCADE,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    snapshots_added INTEGER     NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.product_latest (
    number TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    file_date DATE NOT NULL,
    date_modified TIMESTAMP NULL,
    row_hash CHAR(64) NOT NULL
);

CREATE OR REPLACE FUNCTION staging.filter_latest_json(j JSONB)
RETURNS JSONB AS $$
BEGIN
    RETURN j - 'toggle_select' - 'vehicle_model';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

INSERT INTO staging.product_latest (number, data, file_date, date_modified, row_hash)
SELECT
    ph.number,
    staging.filter_latest_json(ph.data),
    ph.file_date,
    ph.date_modified,
    ph.row_hash
FROM (
    SELECT DISTINCT ON (number) *
    FROM staging.product_history
    WHERE is_current = TRUE
    ORDER BY number, file_date DESC
) ph;

CREATE INDEX IF NOT EXISTS idx_product_latest_number
    ON staging.product_latest (number);

CREATE INDEX IF NOT EXISTS idx_product_latest_row_hash
    ON staging.product_latest (row_hash);

CREATE OR REPLACE FUNCTION staging.jsonb_diff(a JSONB, b JSONB)
RETURNS JSONB AS $$
DECLARE
    result JSONB := '{}'::jsonb;
    key TEXT;
    val_a JSONB;
    val_b JSONB;
BEGIN
    FOR key IN SELECT jsonb_object_keys(a)
    LOOP
        val_a := a -> key;
        val_b := b -> key;

        IF val_b IS NULL THEN
            result := result || jsonb_build_object(key, jsonb_build_object('from', val_a, 'to', NULL));
        ELSIF val_a IS DISTINCT FROM val_b THEN
            result := result || jsonb_build_object(key, jsonb_build_object('from', val_a, 'to', val_b));
        END IF;
    END LOOP;

    FOR key IN SELECT jsonb_object_keys(b)
    LOOP
        IF a -> key IS NULL THEN
            result := result || jsonb_build_object(key, jsonb_build_object('from', NULL, 'to', b -> key));
        END IF;
    END LOOP;

    RETURN result;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- # Get all snapshots for a product
-- SELECT *
-- FROM staging.product_history
-- WHERE number = 'PRODUCT_NUMBER'
-- ORDER BY file_date, date_modified;

-- # Get the current snapshot for a product
-- SELECT *
-- FROM staging.product_history
-- WHERE number = 'PRODUCT_NUMBER' AND is_current = TRUE;

-- # Get the diff between two snapshots
-- WITH versions AS (
--     SELECT *,
--            ROW_NUMBER() OVER (PARTITION BY number ORDER BY file_date DESC, id DESC) AS rn
--     FROM staging.product_history
--     WHERE number = 'PRODUCT_NUMBER'
-- )
-- SELECT staging.jsonb_diff(
--            staging.filter_latest_json(v2.data),
--            staging.filter_latest_json(v1.data)
--        ) AS diff
-- FROM versions v1       -- latest
-- JOIN versions v2 ON v1.number = v2.number AND v2.rn = v1.rn + 1   -- previous snapshot
-- WHERE v1.rn = 1;      -- latest record