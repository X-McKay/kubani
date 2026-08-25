#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly expected_version=${1:?expected Authentik version is required}
readonly shared_dir=/work/shared
readonly log_file=${shared_dir}/authentik-${expected_version}.log

export AUTHENTIK_DISABLE_UPDATE_CHECK=true
export AUTHENTIK_LISTEN__HTTP=127.0.0.1:9000
export AUTHENTIK_POSTGRESQL__HOST=postgresql.database.svc.cluster.local
export AUTHENTIK_POSTGRESQL__PORT=5432
export AUTHENTIK_POSTGRESQL__NAME=authentik
export AUTHENTIK_POSTGRESQL__USER=authentik

child_pid=
stop_server() {
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill -TERM "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi
}
trap stop_server EXIT TERM INT

if [[ ! -s "${shared_dir}/baseline-counts" ]]; then
  echo "ERROR: exact post-alignment baseline evidence is absent"
  exit 2
fi

echo "Starting live Authentik ${expected_version} lifecycle"
/lifecycle/ak server >"${log_file}" 2>&1 &
child_pid=$!

ready=false
for _ in $(seq 1 180); do
  if grep -Eq \
    'IntegrityError|InconsistentMigrationHistory|FieldError|gunicorn failed to start' \
    "${log_file}"; then
    echo "ERROR: Authentik ${expected_version} reported a migration startup failure"
    exit 1
  fi
  if ! kill -0 "${child_pid}" 2>/dev/null; then
    echo "ERROR: Authentik ${expected_version} exited before readiness"
    exit 1
  fi
  if python3 -c 'from urllib.request import urlopen; urlopen("http://127.0.0.1:9000/-/health/ready/", timeout=2).read()' \
    >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done
if [[ "${ready}" != true ]]; then
  echo "ERROR: Authentik ${expected_version} did not become ready"
  exit 1
fi

if ! /lifecycle/ak migrate --check \
  >"${shared_dir}/migration-check-${expected_version}.log" 2>&1; then
  echo "ERROR: Authentik ${expected_version} reports pending migrations"
  exit 1
fi
echo "PASS: Authentik ${expected_version} is ready with no pending migrations"
