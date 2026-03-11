# Development Workflow Rule

When making code changes that will be deployed:

1. **Test locally first** before shipping
   - Use egress config (`config/local.yaml` or `.env`) to test against cluster services
   - Run `just test-unit` and `just lint` before proceeding
   - For prompt/behavior changes: run the agent locally and verify the change works

2. **Ship via `kubani ship`** — this is the primary deployment command
   - `kubani ship <component>` runs the full pipeline: bump version -> test -> build -> push -> patch manifest -> commit -> git push -> verify
   - `kubani ship <component> --dry-run` to validate tests without deploying
   - `kubani ship <component> --skip-test` if you already tested locally
   - `kubani ship --list` to see all shippable components

3. **Never manually edit deployment manifests** to update image tags
   - `kubani ship` handles manifest patching, version bumping, and git commit/push
   - Manual edits bypass version tracking and pre-commit hooks

4. **If ship fails**, read the output — it stops at the failing step with a clear message
   - Test failure: fix the test, ship again
   - Pre-commit hook failure: fix the issue, ship again
   - Verify failure: check pod logs, fix forward with another ship
