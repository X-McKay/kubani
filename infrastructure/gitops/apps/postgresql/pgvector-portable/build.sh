#!/bin/bash
# Build a portable (x86-64-v2) pgvector 0.8.2 vector.so against the exact
# PG 18.3 headers from the bitnami image digest postgresql-0 runs, but with
# glibc 2.36 (debian bookworm) so no >2.36 versioned symbols leak in.
# (Building inside the Photon image fails: tdnf upgrades glibc to 2.38 and
# _GNU_SOURCE pulls in __isoc23_strtol@GLIBC_2.38, absent at runtime.)
set -euxo pipefail
IMG="docker.io/bitnami/postgresql@sha256:e93732718bf7fafa61a04abaa437fc601c80a791857105fd6fca18407b5725c9"
OUT="$(dirname "$(readlink -f "$0")")"
if [ ! -d "$OUT/bitnami-tree" ]; then
  docker rm -f pgx-extract >/dev/null 2>&1 || true
  docker create --name pgx-extract "$IMG" >/dev/null
  docker cp pgx-extract:/opt/bitnami "$OUT/bitnami-tree"
  docker rm pgx-extract >/dev/null
fi
docker run --rm --user root -v "$OUT/bitnami-tree":/opt/bitnami -v "$OUT":/out debian:bookworm bash -ec '
  apt-get update -qq >/dev/null
  apt-get install -y -qq gcc make wget ca-certificates >/dev/null
  wget -qO /tmp/pgvector.tgz https://github.com/pgvector/pgvector/archive/refs/tags/v0.8.2.tar.gz
  cd /tmp && tar xzf pgvector.tgz && cd pgvector-0.8.2
  make -j"$(nproc)" OPTFLAGS="-march=x86-64-v2" PG_CONFIG=/opt/bitnami/postgresql/bin/pg_config
  cp vector.so /out/vector-portable.so
  sha256sum vector.so
'
