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

CREATE TABLE staging.raw_file (
    id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_date DATE NOT NULL,
    imported_at TIMESTAMPTZ DEFAULT now(),
    row_count INTEGER
);

CREATE TABLE staging.raw_row (
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
