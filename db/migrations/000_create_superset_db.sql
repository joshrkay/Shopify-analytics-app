-- Create separate metadata database for Apache Superset.
-- This keeps Superset metadata isolated from application data.
-- Runs automatically on first docker-compose startup via entrypoint-initdb.d.

SELECT 'CREATE DATABASE superset_metadata OWNER markinsight_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset_metadata')\gexec
