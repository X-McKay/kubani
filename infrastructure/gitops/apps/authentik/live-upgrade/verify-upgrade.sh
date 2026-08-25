#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly live_host=postgresql.database.svc.cluster.local
readonly expected_version=2026.5.6
readonly expected_migrations=717
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

if [[ ! -s "${shared_dir}/baseline-counts" ]]; then
  echo "ERROR: exact post-alignment baseline evidence is absent"
  exit 2
fi
baseline_counts=$(<"${shared_dir}/baseline-counts")
readonly baseline_counts

final_counts=$("${psql_base[@]}" --field-separator='|' --command="
  SELECT
    (SELECT count(*) FROM authentik_core_user),
    (SELECT count(*) FROM authentik_core_group),
    (SELECT count(*) FROM authentik_core_application),
    (SELECT count(*) FROM authentik_core_provider),
    (SELECT count(*) FROM django_migrations);
")
readonly final_counts
IFS='|' read -r final_users final_groups final_apps final_providers final_migrations \
  <<<"${final_counts}"
if [[ "${baseline_counts}" != "${final_users}|${final_groups}|${final_apps}|${final_providers}" ]]; then
  echo "ERROR: identity or provider object counts changed during live migration"
  exit 1
fi
if [[ "${final_migrations}" != "${expected_migrations}" ]]; then
  echo "ERROR: final migration count differs from the rehearsed result"
  exit 1
fi

latest_version=$("${psql_base[@]}" --command="
  SELECT version FROM authentik_version_history
  ORDER BY timestamp DESC, id DESC LIMIT 1;
")
readonly latest_version
waiting_locks=$("${psql_base[@]}" --command="
  SELECT count(*) FROM pg_locks WHERE NOT granted;
")
readonly waiting_locks
active_sessions=$("${psql_base[@]}" --command="
  SELECT count(*) FROM pg_stat_activity
  WHERE datname = 'authentik' AND pid <> pg_backend_pid();
")
readonly active_sessions
repaired_migrations=$("${psql_base[@]}" --field-separator='|' --command="
  SELECT
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_core' AND name = '0056_user_roles'),
    (SELECT count(*) FROM django_migrations
      WHERE app = 'authentik_rbac'
        AND name = '0010_remove_role_group_alter_role_name'),
    (SELECT count(*) FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'authentik_rbac_role'
        AND column_name = 'group_id');
")
readonly repaired_migrations

if [[ "${latest_version}" != "${expected_version}" ]]; then
  echo "ERROR: final version history is not ${expected_version}"
  exit 1
fi
if [[ "${waiting_locks}" != 0 ]]; then
  echo "ERROR: final database has waiting locks"
  exit 1
fi
if [[ "${active_sessions}" != 0 ]]; then
  echo "ERROR: a lifecycle session remained after the final version stopped"
  exit 1
fi
if [[ "${repaired_migrations}" != "1|1|0" ]]; then
  echo "ERROR: repaired migration sequence did not converge"
  exit 1
fi

printf 'PASS: live Authentik upgrade reached %s; users=%s, groups=%s, applications=%s, providers=%s, migrations=%s, waiting locks=0\n' \
  "${expected_version}" "${final_users}" "${final_groups}" \
  "${final_apps}" "${final_providers}" "${final_migrations}"
