# Model release manifests

One reviewed file per model release, `models/<engine>/<name>.yaml`
(contract: `platform/registry/contract/dependencies.md` section 4 in the zetra
repository). The feed carries each as an entry of `modelReleases`; an engine
in `catalog.yaml` states the release it serves with `release: <name>`.

- `name` is the file name without `.yaml`. The release an engine serves when
  this directory was introduced keeps the name the registry already knew it by,
  the slug of its served name (`release_slug` in
  `infrastructure/scripts/ops/registry_feed.py`).
- Every value is read from a file in this repository. A value the repository
  does not state is `null`, which means not recorded. In particular nothing in
  the repository pins the weights, so `weights.revision` and `weights.files`
  are `null` in the two manifests of today.
- A manifest is never edited after it is merged. A change is a new release with
  a new name.
- The renderer refuses an engine whose `release` names no manifest, a manifest
  of another engine, one with another `servedName`, or one whose `engineImage`
  differs from the image of the engine's container. So a new engine image or a
  new served name does not render without a new manifest.
- The embeddings engine has no manifest and no `release`.

Write a new one from the committed state of the engine:

```bash
just inference-manifest --engine fast --name <name> [--weights-revision <rev>] [--benchmark <file>] [--change-record <file>] [--tool-calling true|false]
```

It prints the path and the next steps (the catalog change that moves the engine,
and `just agent alias plan` for an engine behind an alias). The process around
it is in `docs/infrastructure/inference/release-process.md`.
