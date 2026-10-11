\getenv DB_OWNER_ROLE DB_OWNER_ROLE
\getenv DB_SETUP_USER DB_SETUP_USER
\getenv DB_SETUP_PASSWORD DB_SETUP_PASSWORD
\getenv DB_APP_USER DB_APP_USER
\getenv DB_APP_PASSWORD DB_APP_PASSWORD
\getenv DB_MAINTENANCE_USER DB_MAINTENANCE_USER
\getenv DB_MAINTENANCE_PASSWORD DB_MAINTENANCE_PASSWORD
\getenv POSTGRES_USER POSTGRES_USER
\getenv POSTGRES_PASSWORD POSTGRES_PASSWORD

SELECT COUNT(DISTINCT role_name) = 5 AS role_names_are_distinct
FROM unnest(ARRAY[
    :'POSTGRES_USER',
    :'DB_OWNER_ROLE',
    :'DB_SETUP_USER',
    :'DB_APP_USER',
    :'DB_MAINTENANCE_USER'
]) AS roles(role_name)
\gset
\if :role_names_are_distinct
\else
\echo "PostgreSQL administrator, owner, setup, app, and maintenance roles must all have distinct names."
\quit 3
\endif

SELECT format('CREATE ROLE %I WITH LOGIN SUPERUSER', :'POSTGRES_USER')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'POSTGRES_USER'
)
\gexec

ALTER ROLE :"POSTGRES_USER"
    WITH LOGIN SUPERUSER PASSWORD :'POSTGRES_PASSWORD';

SELECT format('CREATE ROLE %I NOLOGIN', :'DB_OWNER_ROLE')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'DB_OWNER_ROLE'
)
\gexec

ALTER ROLE :"DB_OWNER_ROLE"
    WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE', :'DB_SETUP_USER')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'DB_SETUP_USER'
)
\gexec

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE', :'DB_APP_USER')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'DB_APP_USER'
)
\gexec

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE', :'DB_MAINTENANCE_USER')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'DB_MAINTENANCE_USER'
)
\gexec

ALTER ROLE :"DB_SETUP_USER"
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'DB_SETUP_PASSWORD';
ALTER ROLE :"DB_APP_USER"
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'DB_APP_PASSWORD';
ALTER ROLE :"DB_MAINTENANCE_USER"
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'DB_MAINTENANCE_PASSWORD';

GRANT :"DB_OWNER_ROLE", :"DB_MAINTENANCE_USER"
    TO :"DB_SETUP_USER";
GRANT USAGE, CREATE ON SCHEMA public TO :"DB_OWNER_ROLE";
GRANT USAGE, CREATE ON SCHEMA public TO :"DB_MAINTENANCE_USER";

SELECT format('REVOKE %I FROM %I', granted.rolname, member.rolname)
FROM pg_auth_members
JOIN pg_roles AS granted ON granted.oid = pg_auth_members.roleid
JOIN pg_roles AS member ON member.oid = pg_auth_members.member
WHERE member.rolname = :'DB_APP_USER'
  AND granted.rolname IN (:'DB_OWNER_ROLE', :'DB_MAINTENANCE_USER')
\gexec

SET ROLE :"DB_OWNER_ROLE";
CREATE TABLE IF NOT EXISTS applicants (
    p_id BIGSERIAL PRIMARY KEY,
    program TEXT,
    comments TEXT,
    date_added DATE,
    url TEXT UNIQUE,
    status TEXT,
    term TEXT,
    us_or_international TEXT,
    gpa DOUBLE PRECISION,
    gre DOUBLE PRECISION,
    gre_v DOUBLE PRECISION,
    gre_aw DOUBLE PRECISION,
    degree TEXT,
    llm_generated_program TEXT,
    llm_generated_university TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_watermarks (
    source TEXT PRIMARY KEY,
    last_seen TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
RESET ROLE;

ALTER TABLE applicants OWNER TO :"DB_OWNER_ROLE";
ALTER TABLE ingestion_watermarks OWNER TO :"DB_OWNER_ROLE";

REVOKE ALL PRIVILEGES ON applicants FROM PUBLIC;
REVOKE ALL PRIVILEGES ON applicants FROM :"DB_APP_USER";
GRANT SELECT ON applicants TO :"DB_APP_USER";
REVOKE ALL PRIVILEGES ON applicants FROM :"DB_MAINTENANCE_USER";
GRANT SELECT, INSERT, UPDATE, TRUNCATE ON applicants TO :"DB_MAINTENANCE_USER";
REVOKE ALL PRIVILEGES ON ingestion_watermarks FROM :"DB_MAINTENANCE_USER";
GRANT SELECT, INSERT, UPDATE ON ingestion_watermarks TO :"DB_MAINTENANCE_USER";
REVOKE ALL PRIVILEGES ON SEQUENCE applicants_p_id_seq FROM :"DB_MAINTENANCE_USER";
GRANT USAGE, SELECT ON SEQUENCE applicants_p_id_seq TO :"DB_MAINTENANCE_USER";

SELECT format(
    'ALTER MATERIALIZED VIEW %I OWNER TO %I',
    view_name,
    :'DB_MAINTENANCE_USER'
)
FROM unnest(ARRAY[
    'applicant_international_summary',
    'applicant_university_summary',
    'applicant_score_summary'
]) AS views(view_name)
WHERE EXISTS (
    SELECT 1
    FROM pg_class
    WHERE relname = view_name
      AND relkind = 'm'
)
\gexec

SELECT format('REVOKE ALL PRIVILEGES ON %I FROM PUBLIC', view_name)
FROM unnest(ARRAY[
    'applicant_international_summary',
    'applicant_university_summary',
    'applicant_score_summary'
]) AS views(view_name)
WHERE EXISTS (
    SELECT 1
    FROM pg_class
    WHERE relname = view_name
      AND relkind = 'm'
)
\gexec

SELECT format('REVOKE ALL PRIVILEGES ON %I FROM %I', view_name, :'DB_APP_USER')
FROM unnest(ARRAY[
    'applicant_international_summary',
    'applicant_university_summary',
    'applicant_score_summary'
]) AS views(view_name)
WHERE EXISTS (
    SELECT 1
    FROM pg_class
    WHERE relname = view_name
      AND relkind = 'm'
)
\gexec

SELECT format('GRANT SELECT ON %I TO %I', view_name, :'DB_APP_USER')
FROM unnest(ARRAY[
    'applicant_international_summary',
    'applicant_university_summary',
    'applicant_score_summary'
]) AS views(view_name)
WHERE EXISTS (
    SELECT 1
    FROM pg_class
    WHERE relname = view_name
      AND relkind = 'm'
)
\gexec
