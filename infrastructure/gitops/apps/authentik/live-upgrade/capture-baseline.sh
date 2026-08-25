#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly live_host=postgresql.database.svc.cluster.local
readonly pre_alignment_fingerprint='5|2|3|3|1|1|0|1|1|1|0|NO|YES|1|0|0|0|2025.10.3'
readonly post_alignment_fingerprint='5|2|3|3|1|1|0|1|1|0|0|YES|YES|0|0|0|0|2025.10.3'
readonly shared_dir=/work/shared
readonly psql_base=(
  psql
  --host="${live_host}"
  --port=5432
  --username=authentik
  --dbname=authentik
  --set=ON_ERROR_STOP=1
  --no-align
  --tuples-only
)

export PGPASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
export PGCONNECT_TIMEOUT=5

aligned=false
for _ in $(seq 1 180); do
  active_sessions=$("${psql_base[@]}" --command="
    SELECT count(*) FROM pg_stat_activity
    WHERE datname = 'authentik' AND pid <> pg_backend_pid();
  ")
  if [[ "${active_sessions}" != 0 ]]; then
    echo "ERROR: authentik sessions are not fully drained"
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
  if [[ "${fingerprint}" == "${post_alignment_fingerprint}" ]]; then
    aligned=true
    break
  fi
  if [[ "${fingerprint}" != "${pre_alignment_fingerprint}" ]]; then
    echo "ERROR: schema, history, identity counts, or waiting locks differ from both reviewed fingerprints"
    exit 2
  fi
  sleep 5
done
if [[ "${aligned}" != true ]]; then
  echo "ERROR: exact live alignment did not complete within the bounded wait"
  exit 2
fi

mkdir -p "${shared_dir}"
chgrp 2000 "${shared_dir}"
chmod 2770 "${shared_dir}"
printf '%s\n' '5|2|3|3' >"${shared_dir}/baseline-counts"
chgrp 2000 "${shared_dir}/baseline-counts"
chmod 0640 "${shared_dir}/baseline-counts"
echo "PASS: live Authentik post-alignment baseline is exact and fully drained"
