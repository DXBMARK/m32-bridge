# SpecKit execution order for M32 Bridge protocol completion

## Mandatory order

1. `/speckit.constitution` using `speckit-constitution-amendment-v2.md`.
2. Review the constitution diff and synchronization impact report.
3. Commit only the governance amendment after validation.
4. `/speckit.specify` using `speckit-specify-004.md`.
5. Run `/speckit.clarify` and resolve all HIGH-impact ambiguities before planning.
6. Run `/speckit.plan` with the planning constraints below.
7. Review `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, and `plan.md` before task generation.
8. Run `/speckit.tasks` with one ordered phase per P0A-P12 and hard checkpoints.
9. Run `/speckit.analyze` and require zero critical inconsistencies.
10. Execute with `/speckit.implement`, one patch phase only at a time.

## Planning constraints for `/speckit.plan`

- Reuse the existing local Python modular-monolith boundaries.
- Prefer compatibility adapters and additive modules before deleting current paths.
- Do not broaden installer or runtime behavior while P0-P10 are under construction.
- Create versioned contracts for protocol parameters, snapshots, hardware acceptance, maintenance permits, capability evidence, and release evidence.
- Produce a complete dependency graph between P0A-P12.
- Define rollback/migration strategy for each phase.
- Define exact test gates per phase: unit, property, Fake M32, MCP stdio, external emulator, hardware, native OS, and release assets.
- The plan must state which tests may send writes and to which target class.
- No real hardware writes may appear before P10.
- No tag/release tasks may execute before P12 and all predecessors pass.

## Task-generation constraints for `/speckit.tasks`

- Number all new tasks from T001 inside feature 004.
- Include requirement IDs and explicit dependencies in every task.
- Mark truly parallel tasks with `[P]` only when they do not touch the same contract or implementation boundary.
- Every implementation task must have a prior failing test/contract task unless it is documentation-only.
- Every phase ends with a checkpoint task that runs the complete relevant regression gate and records evidence.
- Do not mark existing tests as proof when they use dependency injection that bypasses the real stdio/session path.
- Do not accept skipped external-emulator or hardware tests as passes.
- Do not create tasks that update installed CT/Mac runtimes automatically.

## Implementation cadence

For each patch P0A-P12:

1. Read only the tasks in the current patch.
2. Confirm clean branch and exact base commit.
3. Add/adjust contracts and failing tests.
4. Implement the smallest compatible change.
5. Run focused tests.
6. Run all earlier phase regressions.
7. Inspect diff and prohibited-surface audit.
8. Commit the patch separately.
9. Do not continue if the checkpoint fails.

## Recommended commit subjects

- `refactor(mcp): add server-owned runtime session`
- `fix(safety): bind writes to verified runtime state`
- `feat(osc): add versioned parameter registry`
- `feat(osc): implement protocol-faithful value codecs`
- `feat(reads): complete console read surface`
- `feat(state): persist and bind authoritative snapshots`
- `feat(writes): complete semantic R1-R3 pipeline`
- `feat(verify): implement independent proposal verification`
- `feat(maintenance): add controlled R4 break-glass flow`
- `test(fake-m32): model supported OSC protocol faithfully`
- `test(emulator): expand external integration matrix`
- `test(hardware): add physical M32 acceptance evidence`
- `ci(release): add native clean-host asset matrix`
- `docs(release): finalize governance legal and v0.1.0-rc.1`
