# Backend definition examples

These files are the reference for what `infrastructure/mcp/backends/*.yaml` accepts and refuses. `tests/test_mcp_registry_examples.py` runs every one of them through `model.load_registry`, the loader behind `just mcp check`, so they cannot drift from the code. Nothing here is a registered backend: the loader reads only `infrastructure/mcp/backends/*.yaml`.

- `valid/` holds definitions that must be accepted: `example-minimal.yaml` (required fields only) and `example-full.yaml` (every optional field). A valid example is named after its `name`.
- `invalid/` holds one example per rule. Each breaks exactly one rule and sits beside `<name>.expect.json` with the exception type and a distinctive substring of the message. The two examples that are deliberately not parseable YAML are named `*.yaml.txt` so the YAML linters skip them; the test installs them as `.yaml`. A rule about the set of backends (`role-collision`, `credential-pair-collision`) is a directory of backend files instead of one file.
- `support/` holds the non-secret files a definition points at (bootstrap Jobs and SQL), laid out as a repository root. The test also writes fake "encrypted" Secret manifests (`api-token`, `db-role`, `db-workload` and a few deliberately defective ones) into the same throwaway root; none is a real Secret.

To add a rule: add the check to `model.py`, add an invalid example and its `.expect.json`. The test fails if a message raised in `model.py` has no example, or if an example and its expectation do not pair up.

The `existing-streamable-http-v1` profile is bound to specific committed manifests and their hashes, so it has no valid example here; its early field checks have `http-profile-*` examples and the rest is covered by `tests/test_mcp_registry_references.py`.
