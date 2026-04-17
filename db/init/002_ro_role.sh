#!/bin/bash
# Read-only role used by the natural-language-query endpoint.
#
# The app owner keeps full privileges for schema migrations and seed
# inserts. Anything driven by user-entered text instead connects as
# ${POSTGRES_RO_USER}, which can only SELECT. Even if the LLM emits
# "DROP TABLE prices" Postgres refuses at permission-check time.
#
# This is a shell script (not plain .sql) because psql's :variable
# substitution doesn't reach inside dollar-quoted DO blocks — we need
# bash + psql -v variables to thread POSTGRES_RO_USER / _PASSWORD from
# the container env into DDL that runs exactly once on first init.

set -euo pipefail

: "${POSTGRES_DB:?POSTGRES_DB not set}"
: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_RO_USER:=app_ro}"
: "${POSTGRES_RO_PASSWORD:=app_ro}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname   "$POSTGRES_DB" \
     --set="ro_user=$POSTGRES_RO_USER" \
     --set="ro_password=$POSTGRES_RO_PASSWORD" \
     --set="db=$POSTGRES_DB" <<'EOSQL'
-- Build and run CREATE ROLE via \gexec. This lets us use psql's :var
-- substitution (which doesn't work inside DO $$ ... $$ blocks) and stay
-- idempotent if the script is ever re-run on a fresh volume.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'ro_user', :'ro_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'ro_user')
\gexec

-- Ensure the password matches the current env value even if the role
-- already existed (e.g. rotated password across redeploys, though the
-- init dir only runs on a fresh cluster).
ALTER ROLE :"ro_user" WITH PASSWORD :'ro_password';

GRANT CONNECT ON DATABASE :"db" TO :"ro_user";
GRANT USAGE   ON SCHEMA public  TO :"ro_user";

GRANT SELECT ON ALL TABLES    IN SCHEMA public TO :"ro_user";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO :"ro_user";

-- Any table created after this point should automatically be
-- SELECT-able by the read-only role without a follow-up grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES    TO :"ro_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON SEQUENCES TO :"ro_user";

-- Per-role statement timeout. The API also sets SET LOCAL per query for
-- tighter bounds, but this is a safety net if someone bypasses that path.
ALTER ROLE :"ro_user" SET statement_timeout = '10s';
ALTER ROLE :"ro_user" SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE :"ro_user" SET default_transaction_read_only = on;
EOSQL
