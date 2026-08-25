#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly backup_dir=/backups/postgresql
readonly backup_name=authentik-live-alignment-v1-20260825.sql.gz.enc
readonly backup_file=${backup_dir}/${backup_name}
readonly checksum_file=${backup_file}.sha256
readonly partial_file=${backup_file}.partial
readonly checksum_partial=${checksum_file}.partial
readonly work_dir=/work
readonly socket_dir=${work_dir}/socket
readonly live_host=postgresql.database.svc.cluster.local
readonly live_port=5432
readonly live_user=postgres
readonly expected_fingerprint='5|2|3|3|1|1|0|1|1|1|0|NO|YES|1|0|0|0|2025.10.3'

export PGPASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
export PGCONNECT_TIMEOUT=5

pg_started=false
cleanup() {
  rm -f "${partial_file}" "${checksum_partial}"
  if [[ "${pg_started}" == true ]]; then
    pg_ctl --pgdata="${PGDATA}" --mode=fast --wait stop >/dev/null || true
  fi
}
trap cleanup EXIT

fingerprint() {
  local pg_host=$1
  local pg_port=$2
  local pg_user=$3
  psql --host="${pg_host}" --port="${pg_port}" --username="${pg_user}" \
    --dbname=authentik --tuples-only --no-align --field-separator='|' \
    --set=ON_ERROR_STOP=1 --command="
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
    "
}

mkdir -p "${backup_dir}" "${work_dir}" "${socket_dir}" "${work_dir}/tmp"
chmod 0700 "${work_dir}" "${socket_dir}" "${work_dir}/tmp"
if [[ -e "${backup_file}" || -e "${checksum_file}" \
  || -e "${partial_file}" || -e "${checksum_partial}" ]]; then
  echo "ERROR: reviewed backup target already exists"
  exit 2
fi

live_before=$(fingerprint "${live_host}" "${live_port}" "${live_user}")
readonly live_before
if [[ "${live_before}" != "${expected_fingerprint}" ]]; then
  echo "ERROR: live Authentik fingerprint differs from the reviewed state"
  exit 2
fi

echo "Creating fixed-name encrypted PostgreSQL recovery point on rig0"
pg_dumpall --host="${live_host}" --port="${live_port}" \
  --username="${live_user}" --clean --if-exists \
  | gzip -9 \
  | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -md sha256 \
      -pass env:POSTGRES_PASSWORD -out "${partial_file}"

backup_size=$(stat -c%s "${partial_file}")
readonly backup_size
if (( backup_size < 1024 )); then
  echo "ERROR: encrypted backup is unexpectedly small"
  exit 1
fi
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -pass env:POSTGRES_PASSWORD -in "${partial_file}" | gzip -t
mv "${partial_file}" "${backup_file}"
(
  cd "${backup_dir}"
  sha256sum "${backup_name}" >"${checksum_partial}"
)
mv "${checksum_partial}" "${checksum_file}"
(
  cd "${backup_dir}"
  sha256sum --check "${backup_name}.sha256"
)

live_after=$(fingerprint "${live_host}" "${live_port}" "${live_user}")
readonly live_after
if [[ "${live_after}" != "${live_before}" ]]; then
  echo "ERROR: live Authentik fingerprint changed while the backup was created"
  exit 1
fi

export PGDATA=${work_dir}/pgdata
export TMPDIR=${work_dir}/tmp
runtime_uid=$(id -u)
readonly runtime_uid
if ! getent passwd "${runtime_uid}" >/dev/null; then
  echo "ERROR: runtime UID is absent from the container identity database"
  exit 2
fi
restore_role=authentik_preflight_$(openssl rand -hex 12)
readonly restore_role
initdb --pgdata="${PGDATA}" --username="${restore_role}" \
  --auth-local=trust --auth-host=reject >/dev/null
pg_ctl --pgdata="${PGDATA}" \
  --options="-c listen_addresses='' -c unix_socket_directories=${socket_dir} -c port=5433 -c log_statement=none -c log_min_error_statement=panic" \
  --wait start >/dev/null
pg_started=true

echo "Restoring the fresh recovery point into isolated PostgreSQL"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -pass env:POSTGRES_PASSWORD -in "${backup_file}" \
  | gzip -dc \
  | psql --host="${socket_dir}" --port=5433 --username="${restore_role}" \
      --dbname=postgres --set=ON_ERROR_STOP=1 --quiet

restored_fingerprint=$(fingerprint "${socket_dir}" 5433 "${restore_role}")
readonly restored_fingerprint
if [[ "${restored_fingerprint}" != "${live_before}" ]]; then
  echo "ERROR: isolated restore does not match the reviewed live fingerprint"
  exit 1
fi

waiting_locks=$(psql --host="${socket_dir}" --port=5433 \
  --username="${restore_role}" --dbname=authentik --tuples-only --no-align \
  --command="SELECT count(*) FROM pg_locks WHERE NOT granted")
readonly waiting_locks
if [[ "${waiting_locks}" != 0 ]]; then
  echo "ERROR: isolated restore has a waiting lock"
  exit 1
fi

echo "PASS: fresh encrypted backup restored and live-alignment fingerprint verified; backup=${backup_name}; bytes=${backup_size}; waiting_locks=0"
