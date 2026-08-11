# Portable pgvector overlay

`pgvector-portable-configmap.yaml` carries a rebuilt `vector.so` (pgvector
0.8.2, PG 18.3) mounted over the copy baked into `bitnami/postgresql`.

## Why

The bitnami image's `vector.so` mixes AVX-512VL instructions (e.g.
`vextractf64x2` in `vector_norm`'s reduction tail) into otherwise-AVX2
functions. The database nodes' CPUs (strix: Ryzen 7 3750H, Zen+) have no
AVX-512, so the first HNSW insert or index scan hits an illegal instruction
(SIGILL), killing the backend and taking the whole server through crash
recovery — observed live 2026-08-09 16:38 GMT (bakudo issue #30). Plain
seq-scan distance queries don't crash, which is why the problem only
surfaced once an HNSW index existed. Faulting instruction confirmed via
node dmesg: offset `0x1fbb1` in `vector.so` = `vextractf64x2` inside
`vector_norm` (HNSW cosine ops normalize on insert/search).

## The fix

`build.sh` rebuilds the identical pgvector 0.8.2 source with
`OPTFLAGS="-march=x86-64-v2"` against the exact image digest's PG headers.
Build quirks it handles:

- Building inside the Photon image upgrades glibc to 2.38, leaking a
  `__isoc23_strtol@GLIBC_2.38` reference (from `_GNU_SOURCE` + new glibc
  headers) that the runtime image (glibc 2.36) can't satisfy — so the
  build runs in `debian:bookworm` (glibc 2.36) with the image's
  `/opt/bitnami` tree mounted at the same path.
- The result keeps AVX-512/F16C code only inside pgvector's own
  runtime-dispatched kernels (verified with objdump: EVEX confined to
  `Bit*Avx512Popcount`).

Verified on a throwaway pod on strix (same image digest, same ConfigMap
mount mechanism): the previously-crashing schema (vector(1024) + HNSW,
insert + cosine scan) plus IVFFlat/halfvec/bit-distance sweeps all pass;
stock `.so` reproducibly SIGILLed the same scenario.

## Upgrading the image

The HelmRelease pins the image by digest so `:latest` can't roll the PG
major out from under this overlay (an ABI-mismatched `.so` fails to load,
breaking all vector ops). To upgrade: bump the digest in
`helmrelease.yaml`, update `IMG` in `build.sh`, rerun it, regenerate the
ConfigMap manifest:

```sh
./build.sh
kubectl create configmap pgvector-portable -n database \
  --from-file=vector.so=vector-portable.so --dry-run=client -o yaml \
  > ../pgvector-portable-configmap.yaml   # re-add the header comment
```

Drop the overlay entirely once the upstream image ships a portable
pgvector build (check: `objdump -d vector.so` → EVEX/`%zmm` outside the
`*Avx512*` dispatched kernels means still broken).
