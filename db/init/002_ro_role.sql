-- Read-only role used by the natural-language-query endpoint.
--
-- The app owner (set by POSTGRES_USER) keeps full privileges for schema
-- migrations and seed inserts. Anything driven by user-entered text
-- instead connects as gam_ro, which can only SELECT. Even if the LLM
-- emits "DROP TABLE prices" Postgres refuses at permission-check time.
--
-- We still add statement timeouts and a LIMIT clause in the API layer —
-- this role is the innermost defence, not the only one.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gam_ro') THEN
        CREATE ROLE gam_ro LOGIN PASSWORD 'gam_ro';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE gam TO gam_ro;
GRANT USAGE ON SCHEMA public TO gam_ro;

GRANT SELECT ON ALL TABLES    IN SCHEMA public TO gam_ro;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO gam_ro;

-- Any table created after this point (e.g. a future migration) should
-- automatically be SELECT-able by gam_ro without a follow-up grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES    TO gam_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON SEQUENCES TO gam_ro;

-- Per-role statement timeout. The API also sets SET LOCAL per query for
-- tighter bounds, but this is a safety net if someone bypasses that path.
ALTER ROLE gam_ro SET statement_timeout = '10s';
ALTER ROLE gam_ro SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE gam_ro SET default_transaction_read_only = on;
