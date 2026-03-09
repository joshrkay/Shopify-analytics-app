#!/bin/bash
set -e

# Create separate metadata database for Apache Superset.
# Uses shell script instead of .sql to avoid transaction-context issues
# with CREATE DATABASE (cannot run inside a transaction block).

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE superset_metadata OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset_metadata')\gexec
EOSQL
