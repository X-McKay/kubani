#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly backup_dir=/backups/postgresql
readonly backup_name=authentik-live-alignment-v1-20260825.sql.gz.enc
readonly backup_file=${backup_dir}/${backup_name}
readonly checksum_file=${backup_file}.sha256
readonly live_host=postgresql.database.svc.cluster.local
readonly expected_fingerprint='5|2|3|3|1|1|0|1|1|1|0|NO|YES|1|0|0|0|2025.10.3'
readonly psql_base=(
  psql
  --host="${live_host}"
  --port=5432
  --username=postgres
  --dbname=authentik
  --set=ON_ERROR_STOP=1
  --no-align
  --tuples-only
)

export PGPASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
export PGCONNECT_TIMEOUT=5

if [[ ! -s "${backup_file}" || ! -s "${checksum_file}" ]]; then
  echo "ERROR: reviewed preflight backup or checksum is absent"
  exit 2
fi
(
  cd "${backup_dir}"
  sha256sum --check "${backup_name}.sha256"
)
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -pass env:POSTGRES_PASSWORD -in "${backup_file}" | gzip -t

active_sessions=1
for _ in $(seq 1 60); do
  active_sessions=$("${psql_base[@]}" --command="
    SELECT count(*) FROM pg_stat_activity
    WHERE datname = 'authentik' AND pid <> pg_backend_pid();
  ")
  if [[ "${active_sessions}" == 0 ]]; then
    break
  fi
  sleep 5
done
readonly active_sessions
if [[ "${active_sessions}" != 0 ]]; then
  echo "ERROR: authentik sessions did not drain; deployment shutdown is unproven"
  exit 2
fi

fingerprint=$("${psql_base[@]}" --field-separator='|' --command="
  SELECT
    (SELECT count(*) FROM authentik_core_user),
    (SELECT count(*) FROM authentik_core_group),
    (SELECT count(*) FROM authentik_core_application),
    (SELECT count(*) FROM authentik_core_provider),
    (SELECT count(*) FROM authentik_rbac_role),
    (SELECT count(*) FROM authentik_rbac_role WHERE group_id IS NOT NULL),
    (SELECT count(*) FROM (
      SELECT name FROM authentik_rbac_role GROUP BY name HAVING count(*) > 1
    ) duplicate_names),
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_rbac' AND name = '0008_alter_role_group'),
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_rbac' AND name = '0009_remove_initialpermissions_mode'),
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_rbac'
        AND name = '0010_remove_role_group_alter_role_name'),
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_core' AND name = '0056_user_roles'),
    (SELECT is_nullable FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_role' AND column_name = 'group_id'),
    (SELECT is_nullable FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_role' AND column_name = 'managed'),
    (SELECT count(*) FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_initialpermissions'
        AND column_name = 'mode'),
    (SELECT count(*) FROM authentik_rbac_initialpermissions),
    (SELECT CASE WHEN to_regclass('public.authentik_core_user_roles') IS NULL
      THEN 0 ELSE 1 END),
    (SELECT count(*) FROM pg_locks WHERE NOT granted),
    (SELECT version FROM authentik_version_history
      ORDER BY timestamp DESC, id DESC LIMIT 1);
")
readonly fingerprint
if [[ "${fingerprint}" != "${expected_fingerprint}" ]]; then
  echo "ERROR: live schema/history differs from the reviewed repair fingerprint"
  exit 2
fi

before_counts=$("${psql_base[@]}" --field-separator='|' --command="
  SELECT
    (SELECT count(*) FROM authentik_rbac_role),
    (SELECT count(*) FROM authentik_rbac_role WHERE group_id IS NOT NULL),
    (SELECT count(*) FROM authentik_core_user),
    (SELECT count(*) FROM authentik_core_group),
    (SELECT count(*) FROM authentik_core_application),
    (SELECT count(*) FROM authentik_core_provider);
")
readonly before_counts

echo "Applying the exact reviewed alignment transaction to live Authentik"
if ! "${psql_base[@]}" <<'SQL'
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT pg_advisory_xact_lock(hashtext('kubani-authentik-live-alignment-v1'));
DO $repair$
DECLARE
  applied_0008 integer;
  applied_0009 integer;
  applied_0010 integer;
  applied_0056 integer;
  deleted_rows integer;
  group_nullable text;
  managed_nullable text;
  authentik_sessions integer;
BEGIN
  SELECT count(*) INTO authentik_sessions
  FROM pg_stat_activity
  WHERE datname = 'authentik' AND pid <> pg_backend_pid();
  SELECT count(*) INTO applied_0008 FROM django_migrations
  WHERE app = 'authentik_rbac' AND name = '0008_alter_role_group';
  SELECT count(*) INTO applied_0009 FROM django_migrations
  WHERE app = 'authentik_rbac' AND name = '0009_remove_initialpermissions_mode';
  SELECT count(*) INTO applied_0010 FROM django_migrations
  WHERE app = 'authentik_rbac'
    AND name = '0010_remove_role_group_alter_role_name';
  SELECT count(*) INTO applied_0056 FROM django_migrations
  WHERE app = 'authentik_core' AND name = '0056_user_roles';
  SELECT is_nullable INTO group_nullable FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'authentik_rbac_role' AND column_name = 'group_id';
  SELECT is_nullable INTO managed_nullable FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'authentik_rbac_role' AND column_name = 'managed';

  IF authentik_sessions <> 0
    OR applied_0008 <> 1 OR applied_0009 <> 1 OR applied_0010 <> 1
    OR applied_0056 <> 0 OR group_nullable IS DISTINCT FROM 'NO'
    OR managed_nullable IS DISTINCT FROM 'YES'
    OR to_regclass('public.authentik_core_user_roles') IS NOT NULL
    OR NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_initialpermissions'
        AND column_name = 'mode'
    )
    OR EXISTS (SELECT 1 FROM authentik_rbac_initialpermissions LIMIT 1)
  THEN
    RAISE EXCEPTION 'live schema/history does not match the reviewed repair fingerprint';
  END IF;

  ALTER TABLE authentik_rbac_role ALTER COLUMN group_id DROP NOT NULL;
  ALTER TABLE authentik_rbac_initialpermissions DROP COLUMN mode;
  DELETE FROM django_migrations
  WHERE app = 'authentik_rbac'
    AND name = '0010_remove_role_group_alter_role_name';
  GET DIAGNOSTICS deleted_rows = ROW_COUNT;
  IF deleted_rows <> 1 THEN
    RAISE EXCEPTION 'expected exactly one premature migration marker';
  END IF;

  IF (SELECT is_nullable FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_role' AND column_name = 'group_id') <> 'YES'
    OR EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_initialpermissions'
        AND column_name = 'mode'
    )
    OR EXISTS (
      SELECT 1 FROM django_migrations
      WHERE app = 'authentik_rbac'
        AND name = '0010_remove_role_group_alter_role_name'
    )
  THEN
    RAISE EXCEPTION 'live repair postcondition failed inside transaction';
  END IF;
END
$repair$;
COMMIT;
SQL
then
  echo "ERROR: exact-fingerprint live alignment failed and PostgreSQL rolled back"
  exit 1
fi

after_counts=$("${psql_base[@]}" --field-separator='|' --command="
  SELECT
    (SELECT count(*) FROM authentik_rbac_role),
    (SELECT count(*) FROM authentik_rbac_role WHERE group_id IS NOT NULL),
    (SELECT count(*) FROM authentik_core_user),
    (SELECT count(*) FROM authentik_core_group),
    (SELECT count(*) FROM authentik_core_application),
    (SELECT count(*) FROM authentik_core_provider);
")
readonly after_counts
if [[ "${after_counts}" != "${before_counts}" ]]; then
  echo "ERROR: live alignment changed domain row counts"
  exit 1
fi

repair_state=$("${psql_base[@]}" --field-separator='|' --command="
  SELECT
    (SELECT is_nullable FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_role' AND column_name = 'group_id'),
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_rbac'
        AND name = '0010_remove_role_group_alter_role_name'),
    (SELECT count(*) FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_initialpermissions'
        AND column_name = 'mode'),
    (SELECT count(*) FROM pg_locks WHERE NOT granted);
")
readonly repair_state
if [[ "${repair_state}" != "YES|0|0|0" ]]; then
  echo "ERROR: live alignment postcondition failed"
  exit 1
fi

echo "PASS: live Authentik migration state aligned; recovery_backup=${backup_name}; domain_counts=${after_counts}; waiting_locks=0"
