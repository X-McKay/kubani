# Explicit model-free agents and complete preflight coverage

User requested fixing all remaining agent preflight issues with Sol subagents.
The three deterministic fixtures currently declare one-token inference grants,
which intentionally cannot satisfy the backend reservation. Raising those budgets
would grant inference authority. Preserve the no-model contract by declaring
`model: null` explicitly in source manifests and `capabilities.models: []` in
source and GitOps Agent definitions.

Source layout validation distinguishes explicit null from accidental omission:
null requires an exact empty grants list; ordinary models must still be granted.
No fixture-name exception or budget-check exemption. The existing pinned SDK
fixture overrides support manifests without usable model configuration. Their
image verifiers must assert the explicit null declaration. Runtime behavior,
tools, identity modes, resource limits, and qualification requirements stay intact.

Execution:
1. Sol source author implements validation, fixture declarations, image assertions,
   documentation and regression tests; runs required source checks.
2. Independent Sol review checks authorization boundaries and fixture contracts.
3. Root runs the actual offline CLI for all thirteen agents against clean source
   and candidate GitOps; preserve both failed and passing receipts.
4. Merge source through gh after CI. Publish lifecycle v0.1.1, performance v0.1.1,
   transport v0.1.2 serially from the merged revision.
5. Stage exact new signed release assets unapproved with the changed Agent
   definitions. Preserve historical release records and failed reports.
6. Verify controller signature, all five attestations, exact policy and NoDrift;
   then separately approve the new releases and update current fixture references.
7. Verify final source compatibility and readiness. Do not run functional
   qualifications, start host capture, restart engines/brokers, or reset ledgers.

Acceptance: all thirteen offline preflights pass; ordinary missing/unauthorized
models and undersized model budgets still fail; deterministic policies have no
inference routes. Preflight success does not assert functional qualification.

Release-infrastructure correction: lifecycle's first publication attempt failed
during apt with memory allocation failure; the unchanged retry failed downloading
git. Root observed guest eth0 MTU 1230 versus Docker bridge MTU 1500, while
runner-level public downloads completed promptly. Kubani PR #401 makes dind
inherit the validated guest MTU through the original pinned entrypoint. Focused
tests, independent review and CI passed; Flux/Helm applied it. A fresh runner
showed both interfaces at 1230. Historical OOM causality remains unproven and
both failed attempts are retained. No engine/broker restart or guard change.
