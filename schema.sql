-- CrownPipe Database Schema
-- PostgreSQL 16+

-- Create database (run as postgres user)
-- CREATE DATABASE crown_marketing OWNER postgres ENCODING 'UTF8';

-- Create role
CREATE ROLE crown_admin
    LOGIN
    PASSWORD 'CHANGE_ME'
    CREATEDB;

-- Grant permissions
GRANT CONNECT, TEMPORARY ON DATABASE crown_marketing TO crown_admin;

-- ========================================
-- Staging Schema (Data Pipeline)
-- ========================================

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

-- ========================================
-- Audit Schema (Media Pipeline)
-- ========================================

CREATE SCHEMA IF NOT EXISTS audit;
GRANT USAGE, CREATE ON SCHEMA audit TO crown_admin;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA audit TO crown_admin;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA audit TO crown_admin;

-- Product audit table
CREATE TABLE IF NOT EXISTS audit.product_audit (
    id BIGSERIAL PRIMARY KEY,
    product_number VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id VARCHAR(100),
    action VARCHAR(100) NOT NULL,
    details TEXT,
    source_file VARCHAR(255),
    execution_time_ms INTEGER,
    context JSONB
);

CREATE INDEX IF NOT EXISTS idx_product_audit_number 
ON audit.product_audit(product_number, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_product_audit_action 
ON audit.product_audit(action);

-- Format history table
CREATE TABLE IF NOT EXISTS audit.format_history (
    id BIGSERIAL PRIMARY KEY,
    product_number VARCHAR(100) NOT NULL,
    format_name VARCHAR(100) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    file_path TEXT,
    file_size_bytes BIGINT
);

CREATE INDEX IF NOT EXISTS idx_format_history_number 
ON audit.format_history(product_number);

-- Production sync table
CREATE TABLE IF NOT EXISTS audit.production_sync (
    id BIGSERIAL PRIMARY KEY,
    product_number VARCHAR(100) NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    files_synced INTEGER NOT NULL,
    total_bytes BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_production_sync_number 
ON audit.production_sync(product_number, synced_at DESC);

-- ========================================
-- Logs Schema (System Logging)
-- ========================================

CREATE SCHEMA IF NOT EXISTS logs;
GRANT USAGE, CREATE ON SCHEMA logs TO crown_admin;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA logs TO crown_admin;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA logs TO crown_admin;

CREATE TABLE IF NOT EXISTS logs.pipeline_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level VARCHAR(20) NOT NULL,
    pipeline VARCHAR(50),
    module VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    exception TEXT,
    user_id VARCHAR(100),
    execution_time_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp 
ON logs.pipeline_logs(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_logs_level 
ON logs.pipeline_logs(level);

CREATE INDEX IF NOT EXISTS idx_logs_pipeline 
ON logs.pipeline_logs(pipeline);

CREATE INDEX IF NOT EXISTS idx_logs_module 
ON logs.pipeline_logs(module);

-- View for recent errors
-- CREATE OR REPLACE VIEW logs.recent_errors AS
-- SELECT *
-- FROM logs.pipeline_logs
-- WHERE level IN ('ERROR', 'CRITICAL')
--   AND timestamp > NOW() - INTERVAL '24 hours'
-- ORDER BY timestamp DESC;
