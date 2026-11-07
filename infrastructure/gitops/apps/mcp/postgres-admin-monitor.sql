-- Dedicated metadata-only interface in the existing postgres database.
-- Bootstrap only, as postgres. Password is read from env, never psql argv.
\set ON_ERROR_STOP on
\getenv monitor_password MCP_PASSWORD
BEGIN;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
DO $bootstrap$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'db_admin_monitor_owner') THEN
    CREATE ROLE db_admin_monitor_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'db_admin_monitor') THEN
    CREATE ROLE db_admin_monitor LOGIN NOINHERIT;
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_roles
    WHERE rolname IN ('db_admin_monitor_owner', 'db_admin_monitor') AND
      (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR
       (rolname = 'db_admin_monitor_owner' AND rolcanlogin) OR
       (rolname = 'db_admin_monitor' AND (NOT rolcanlogin OR rolinherit)))
  ) THEN
    RAISE EXCEPTION 'unexpected privileged monitor role collision; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_auth_members m
    JOIN pg_catalog.pg_roles member ON member.oid = m.member
    JOIN pg_catalog.pg_roles parent ON parent.oid = m.roleid
    WHERE member.rolname IN ('db_admin_monitor_owner', 'db_admin_monitor')
      AND NOT (member.rolname = 'db_admin_monitor_owner' AND parent.rolname = 'pg_read_all_stats')
  ) THEN
    RAISE EXCEPTION 'unexpected monitor role membership; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid = m.roleid
    WHERE r.rolname IN ('db_admin_monitor_owner', 'db_admin_monitor')
  ) THEN
    RAISE EXCEPTION 'unexpected monitor role consumers; review required';
  END IF;
  -- Direct ACLs/ownership do not disappear with NOINHERIT. Never adopt an
  -- existing role that already has authority beyond this exact interface.
  IF EXISTS (
    SELECT FROM pg_catalog.pg_shdepend d JOIN pg_catalog.pg_roles r ON r.oid = d.refobjid
    WHERE d.refclassid = 'pg_catalog.pg_authid'::pg_catalog.regclass
      AND r.rolname IN ('db_admin_monitor_owner', 'db_admin_monitor')
      AND d.deptype IN ('a', 'o')
      AND NOT (
        (d.dbid = 0 AND d.classid = 'pg_catalog.pg_auth_members'::pg_catalog.regclass)
        OR (d.dbid = 0 AND d.classid = 'pg_catalog.pg_database'::pg_catalog.regclass
            AND d.objid = (SELECT oid FROM pg_catalog.pg_database WHERE datname = 'postgres')
            AND d.deptype = 'a' AND r.rolname = 'db_admin_monitor')
        OR (d.dbid = (SELECT oid FROM pg_catalog.pg_database WHERE datname = pg_catalog.current_database())
            AND (
              (d.classid = 'pg_catalog.pg_namespace'::pg_catalog.regclass
               AND d.objid = (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname = 'db_admin_monitor'))
              OR (d.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass AND d.objid IN
                  (SELECT p.oid FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'db_admin_monitor' AND p.pronargs = 0 AND
                     p.proname IN ('instance_health_fn', 'database_stats_fn', 'connection_summary_fn', 'blocking_summary_fn')))
              OR (d.classid = 'pg_catalog.pg_class'::pg_catalog.regclass AND d.objid IN
                  (SELECT c.oid FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'db_admin_monitor' AND c.relkind = 'v' AND
                     c.relname IN ('instance_health', 'database_stats', 'connection_summary', 'blocking_summary')))
            ))
      )
  ) OR EXISTS (
    SELECT FROM pg_catalog.pg_database d,
      LATERAL pg_catalog.aclexplode(d.datacl) a JOIN pg_catalog.pg_roles r ON r.oid = a.grantee
    WHERE r.rolname IN ('db_admin_monitor_owner', 'db_admin_monitor')
      AND NOT (r.rolname = 'db_admin_monitor' AND d.datname = 'postgres' AND a.privilege_type = 'CONNECT')
  ) THEN
    RAISE EXCEPTION 'unexpected monitor direct privileges or ownership; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname NOT IN ('information_schema', 'db_admin_monitor')
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND (pg_catalog.has_table_privilege('db_admin_monitor', c.oid, 'SELECT')
           OR pg_catalog.has_any_column_privilege('db_admin_monitor', c.oid, 'SELECT'))
  ) THEN
    RAISE EXCEPTION 'existing PUBLIC or direct application-data access; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
    WHERE p.prosecdef AND n.nspname <> 'db_admin_monitor'
      AND pg_catalog.has_function_privilege('db_admin_monitor', p.oid, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'existing executable SECURITY DEFINER outside monitor interface; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_namespace n, LATERAL pg_catalog.aclexplode(n.nspacl) a
    WHERE n.nspname = 'db_admin_monitor'
      AND a.grantee = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'db_admin_monitor')
      AND (a.privilege_type <> 'USAGE' OR a.is_grantable)
  ) OR EXISTS (
    SELECT FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace,
      LATERAL pg_catalog.aclexplode(c.relacl) a
    WHERE n.nspname = 'db_admin_monitor'
      AND a.grantee = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'db_admin_monitor')
      AND (a.privilege_type <> 'SELECT' OR a.is_grantable)
  ) OR EXISTS (
    SELECT FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace,
      LATERAL pg_catalog.aclexplode(p.proacl) a
    WHERE n.nspname = 'db_admin_monitor'
      AND a.grantee = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'db_admin_monitor')
      AND (a.privilege_type <> 'EXECUTE' OR a.is_grantable)
  ) THEN
    RAISE EXCEPTION 'unexpected monitor interface grant; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid = n.nspowner
    WHERE n.nspname = 'db_admin_monitor' AND r.rolname <> 'db_admin_monitor_owner'
  ) THEN
    RAISE EXCEPTION 'unexpected monitor schema owner; review required';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
    WHERE n.nspname = 'db_admin_monitor' AND
      (c.relkind <> 'v' OR r.rolname <> 'db_admin_monitor_owner' OR
       c.relname NOT IN ('instance_health', 'database_stats', 'connection_summary', 'blocking_summary'))
  ) OR EXISTS (
    SELECT FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
    JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
    WHERE n.nspname = 'db_admin_monitor' AND
      (r.rolname <> 'db_admin_monitor_owner' OR p.pronargs <> 0 OR
       p.proname NOT IN ('instance_health_fn', 'database_stats_fn', 'connection_summary_fn', 'blocking_summary_fn'))
  ) THEN
    RAISE EXCEPTION 'unexpected monitor schema objects; review required';
  END IF;
END
$bootstrap$;
ALTER ROLE db_admin_monitor_owner WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  INHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE db_admin_monitor WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 PASSWORD :'monitor_password';
ALTER ROLE db_admin_monitor SET default_transaction_read_only = on;
ALTER ROLE db_admin_monitor SET statement_timeout = '5s';
ALTER ROLE db_admin_monitor SET lock_timeout = '1s';
ALTER ROLE db_admin_monitor SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE db_admin_monitor SET search_path = pg_catalog;
ALTER ROLE db_admin_monitor SET timezone = 'UTC';
GRANT pg_read_all_stats TO db_admin_monitor_owner;
GRANT CONNECT ON DATABASE postgres TO db_admin_monitor;
CREATE SCHEMA IF NOT EXISTS db_admin_monitor AUTHORIZATION db_admin_monitor_owner;
REVOKE ALL ON SCHEMA db_admin_monitor FROM PUBLIC;
REVOKE ALL ON SCHEMA db_admin_monitor FROM db_admin_monitor;
GRANT USAGE ON SCHEMA db_admin_monitor TO db_admin_monitor;

-- No arguments, dynamic SQL, application relation access or raw activity fields.
CREATE OR REPLACE FUNCTION db_admin_monitor.instance_health_fn()
RETURNS TABLE (
  observed_at timestamptz, server_version_num integer, in_recovery boolean,
  uptime_seconds bigint, max_connections integer, database_count bigint
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  SELECT pg_catalog.statement_timestamp(), pg_catalog.current_setting('server_version_num')::integer,
         pg_catalog.pg_is_in_recovery(),
         greatest(0, floor(extract(epoch FROM pg_catalog.statement_timestamp() - pg_catalog.pg_postmaster_start_time())))::bigint,
         pg_catalog.current_setting('max_connections')::integer,
         (SELECT count(*) FROM pg_catalog.pg_database WHERE datallowconn AND NOT datistemplate);
$function$;

CREATE OR REPLACE FUNCTION db_admin_monitor.database_stats_fn()
RETURNS TABLE (
  observed_at timestamptz, database_name text, size_bytes bigint, numbackends integer,
  xact_commit bigint, xact_rollback bigint, blks_read bigint, blks_hit bigint,
  deadlocks bigint, temp_bytes bigint, stats_reset timestamptz
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  SELECT pg_catalog.statement_timestamp(), d.datname::text,
         pg_catalog.pg_database_size(d.oid), s.numbackends,
         s.xact_commit, s.xact_rollback, s.blks_read, s.blks_hit,
         s.deadlocks, s.temp_bytes, s.stats_reset
  FROM pg_catalog.pg_database d
  JOIN pg_catalog.pg_stat_database s ON s.datid = d.oid
  WHERE d.datallowconn AND NOT d.datistemplate
  ORDER BY pg_catalog.pg_database_size(d.oid) DESC, d.datname::text ASC
  LIMIT 16;
$function$;

CREATE OR REPLACE FUNCTION db_admin_monitor.connection_summary_fn()
RETURNS TABLE (
  observed_at timestamptz, state text, wait_event_type text, connections bigint,
  max_transaction_age_seconds bigint, max_query_age_seconds bigint,
  total_groups bigint, total_connections bigint
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  WITH grouped AS (
    SELECT coalesce(a.state, 'unknown') AS state,
           coalesce(a.wait_event_type, 'none') AS wait_event_type, count(*) AS connections,
           max(CASE WHEN a.xact_start IS NOT NULL THEN
             greatest(0, floor(extract(epoch FROM pg_catalog.statement_timestamp() - a.xact_start)))::bigint END)
             AS max_transaction_age_seconds,
           max(CASE WHEN a.state = 'active' AND a.query_start IS NOT NULL THEN
             greatest(0, floor(extract(epoch FROM pg_catalog.statement_timestamp() - a.query_start)))::bigint END)
             AS max_query_age_seconds
    FROM pg_catalog.pg_stat_activity a
    WHERE a.backend_type = 'client backend'
    GROUP BY coalesce(a.state, 'unknown'), coalesce(a.wait_event_type, 'none')
  )
  SELECT pg_catalog.statement_timestamp(), g.state, g.wait_event_type, g.connections,
         g.max_transaction_age_seconds, g.max_query_age_seconds,
         count(*) OVER ()::bigint, sum(g.connections) OVER ()::bigint
  FROM grouped g ORDER BY g.state, g.wait_event_type LIMIT 16;
$function$;

CREATE OR REPLACE FUNCTION db_admin_monitor.blocking_summary_fn()
RETURNS TABLE (
  observed_at timestamptz, blocked_connections bigint, blocking_edges bigint,
  max_blocked_query_age_seconds bigint, max_blocked_transaction_age_seconds bigint,
  oldest_wait_seconds bigint
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  WITH blocked AS MATERIALIZED (
    SELECT a.pid, pg_catalog.cardinality(pg_catalog.pg_blocking_pids(a.pid))::bigint AS edges,
           a.query_start, a.xact_start
    FROM pg_catalog.pg_stat_activity a
    WHERE a.backend_type = 'client backend' AND a.wait_event_type = 'Lock'
  ), waits AS (
    SELECT l.pid, min(l.waitstart) AS waitstart
    FROM pg_catalog.pg_locks l WHERE NOT l.granted GROUP BY l.pid
  )
  SELECT pg_catalog.statement_timestamp(), count(*), coalesce(sum(b.edges), 0)::bigint,
         max(CASE WHEN b.query_start IS NOT NULL THEN
           greatest(0, floor(extract(epoch FROM pg_catalog.statement_timestamp() - b.query_start)))::bigint END),
         max(CASE WHEN b.xact_start IS NOT NULL THEN
           greatest(0, floor(extract(epoch FROM pg_catalog.statement_timestamp() - b.xact_start)))::bigint END),
         max(CASE WHEN w.waitstart IS NOT NULL THEN
           greatest(0, floor(extract(epoch FROM pg_catalog.statement_timestamp() - w.waitstart)))::bigint END)
  FROM blocked b LEFT JOIN waits w ON w.pid = b.pid WHERE b.edges > 0;
$function$;

ALTER FUNCTION db_admin_monitor.instance_health_fn() OWNER TO db_admin_monitor_owner;
ALTER FUNCTION db_admin_monitor.database_stats_fn() OWNER TO db_admin_monitor_owner;
ALTER FUNCTION db_admin_monitor.connection_summary_fn() OWNER TO db_admin_monitor_owner;
ALTER FUNCTION db_admin_monitor.blocking_summary_fn() OWNER TO db_admin_monitor_owner;
REVOKE ALL ON FUNCTION db_admin_monitor.instance_health_fn(), db_admin_monitor.database_stats_fn(),
  db_admin_monitor.connection_summary_fn(), db_admin_monitor.blocking_summary_fn() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION db_admin_monitor.instance_health_fn(), db_admin_monitor.database_stats_fn(),
  db_admin_monitor.connection_summary_fn(), db_admin_monitor.blocking_summary_fn() TO db_admin_monitor;

-- Audited views keep fixed execute_sql statements compatible with the stock
-- restricted parser. Its function-name validation is not a security boundary
-- (RangeFunction traversal differs); grants and these fixed bodies remain so.
CREATE OR REPLACE VIEW db_admin_monitor.instance_health WITH (security_barrier = true)
  AS SELECT * FROM db_admin_monitor.instance_health_fn();
CREATE OR REPLACE VIEW db_admin_monitor.database_stats WITH (security_barrier = true)
  AS SELECT * FROM db_admin_monitor.database_stats_fn();
CREATE OR REPLACE VIEW db_admin_monitor.connection_summary WITH (security_barrier = true)
  AS SELECT * FROM db_admin_monitor.connection_summary_fn();
CREATE OR REPLACE VIEW db_admin_monitor.blocking_summary WITH (security_barrier = true)
  AS SELECT * FROM db_admin_monitor.blocking_summary_fn();
ALTER VIEW db_admin_monitor.instance_health OWNER TO db_admin_monitor_owner;
ALTER VIEW db_admin_monitor.database_stats OWNER TO db_admin_monitor_owner;
ALTER VIEW db_admin_monitor.connection_summary OWNER TO db_admin_monitor_owner;
ALTER VIEW db_admin_monitor.blocking_summary OWNER TO db_admin_monitor_owner;
REVOKE ALL ON db_admin_monitor.instance_health, db_admin_monitor.database_stats,
  db_admin_monitor.connection_summary, db_admin_monitor.blocking_summary FROM PUBLIC, db_admin_monitor;
GRANT SELECT ON db_admin_monitor.instance_health, db_admin_monitor.database_stats,
  db_admin_monitor.connection_summary, db_admin_monitor.blocking_summary TO db_admin_monitor;
COMMIT;
