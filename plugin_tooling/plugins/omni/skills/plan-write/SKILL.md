---
name: plan-write
description: Write an implementation plan (and its tickets) the same way every time. Inventory what already exists, write bite-sized tasks with falsifiable acceptance criteria, apply the doctrine gates and the R1-R8 adversarial pass, register the plan, and report only the link and the decisions. Use for "write a plan", "plan this", or before dispatching design-scale work. For a session handoff use /onex:handoff, which works today.
prosthetic: true
replaces_when: "`onex skill design_to_plan --plan-only` (node_design_to_plan) writes a plan file, returning a non-null `plan_path` with `review_rounds > 0`, on three consecutive topics. On 2026-09-22 a dry run walked idle → brainstorm → structure → review → finalize → launch → done in 93 ms, with plan_path null and review_rounds 0: it is a phase machine that writes nothing."
restored_from: "omniclaude 55913e973^ plugins/onex/skills/writing-plans/SKILL.md (with 8dcb57f1c design_to_plan)"
ticket: OMN-19210
---

# Plan write (prosthetic)

## 0. Where it goes

- Raw, unsettled ideas: docs_repo `beta/plans/_scratch/<YYYY-MM-DD>-<slug>.md`, written
  in a worktree off `origin/main`. registry_root has no carve-out any more: its required `freeze-gate` check refuses
  every new file outside the ledger archive (rule 20, OMN-19625, OMN-19744). A settled idea moves up
  to `beta/plans/` and is registered as below.
- A plan for current work: docs_repo `beta/plans/<YYYY-MM-DD>-<slug>.md`, written in a
  worktree off `origin/main`. Resolve the clone fail-fast: `KB="${DOCS_REPO_PATH:?}"`.
  Add the plan to `beta/plans/PLAN_LIFECYCLE.yaml`, then regenerate `INDEX.md` from the worktree root
  with `python3 scripts/check_plan_index.py --write`, and run it once more without `--write`: exit 0
  means the index matches the registry, and exit 1 means it is stale. CI
  (`.github/workflows/plan-index-registry.yml`) runs `python3 -m unittest tests.test_plan_index_registry -v`
  and then the same script; run both locally before the PR. Both need PyYAML. Never hand-edit the index. The registry's header comment names
  `beta/plans/_engine/regenerate_plan_index.py`, which does not exist. The script's own docstring
  says the renderer and its gate are one file, `scripts/check_plan_index.py`.
- Design-scale work (a new layer, framework or standing system): the operator reviews the plan
  **before** any implementation lane is dispatched. Read-only discovery lanes may run first.

## 1. Inventory before writing (this is what the old skill lacked)

- Grep the ledger and docs_repo (`beta/plans`, `beta/tracking`, `beta/handoffs`) for the
  subject over the last three days, and diff against what you find instead of re-deriving it.
- Search current **and archived** repos for existing code that already does part of it. Most of it
  is usually built.
- For every parent ticket you will decompose, run `list_issues(parentId=...)` first. Existing
  children may encode a newer revision than the document you were handed.
- Every factual premise gets `verified by: <command> => <observation>`, as in the `lane-brief` skill.

## 2. Header

Title; `state_as_of:` with a UTC timestamp; goal (one sentence); the ticket or epic; the existing-asset
inventory as a table (asset, repo, state, reuse or replace); out of scope.

## 3. Tasks

Each task: files touched (exact repo-relative paths); a failing test first; the minimal change; the
focused test command; the lab step (host, lane, what is exercised); and acceptance criteria written as
`<criterion> -- falsifier: <check or command shape>`. That is the form the Linear create guard
accepts, together with a `Gate:` line and a parent. Size tasks so one lane lands each one in a single PR
under one ticket id.

## 4. Doctrine gates

Map each gate that applies to at least one task's acceptance criteria, or flag the plan as not ready:
rendered task content (no placeholder counts), replay determinism, an ordering authority per
projection, deterministic keys plus UPSERT, measured vs estimated cost, one concept per topic,
pure envelopes, FAIL-not-WARN degradation, consumer health, track isolation, durable-queue
contracts, and column ownership for multi-path writes. For a projection, the two-class split in
rule 7a. A gate with no task that fulfils it is a BLOCKER line, not a checkbox.

**Model-before-build (operator ruling, 2026-09-23, RULING row 2026-09-23T14:30:21Z lane=omn17427-foreground, item 4).** A task that builds a
not-yet-built mechanism with a lease, more than one writer, or a terminal it must emit names a TLA+
model of the mechanism and its design-review verdict, or the task is not ready. The model finds the
interleaving; a pytest on the real code is still the gate, never a substitute for the model. The
formal-verification plan (ticket OMN-19204) proposes a harness at omnibase_infra `formal/`, which
does not exist yet — until it lands, the model lives in the building lane's own scratch space, cited
by path in the task. A task with no model and no verdict is a BLOCKER line, not a checkbox (the model-before-build gate).
The lane-brief skill refuses to dispatch such a task without this citation.

## 5. Adversarial pass (R1-R8), fixed inline before anyone sees the plan

- **R1 Count integrity**: recount every "N tasks/phases/tickets" from the list itself, and fix the prose to match.
- **R2 Criteria strength**: replace "superset", "tests pass" and "valid output" with exact lists and fields; ban unmeasured "clean/robust"; resolve every `<placeholder>`.
- **R3 Scope**: a task's stated scope must be able to implement what it claims (a doc edit cannot enforce runtime behaviour).
- **R4 Integration traps**: pin import paths, signatures, topic names and CLI flags to a real call site in the repo; no machine-absolute paths.
- **R5 Idempotency**: state the dedup key and the rerun behaviour for every created resource.
- **R6 Verification**: grade each proof strong, medium or weak; a weak proof never stands alone for a core invariant; prove placement with line order.
- **R7 Expansion**: label a functional expansion and reconcile the docs and callers that relied on the old behaviour.
- **R8 Prerequisites**: list the conditions for each step, and make every unmet condition fail loudly.

## 6. Land and report

Scrub, then commit (`uv run --project "$registry_root/../ops_tooling_pkg" onex-shared-doc-scrub --names-file "$registry_root/../ops_tooling_pkg/vocabularies/person_names.txt" --write <path>`),
open the PR, and land it with the `pr-land` skill (`/omni:pr-land`; `gh pr merge --squash`; no auto-merge in that
repository: `gh api repos/OmniNode-ai/docs_repo --jq .allow_auto_merge` read `false` on
2026-09-23). The message to the operator is the link, one line on what the plan is, and only the
decisions they must make, each asked as a plain question. No digest of the plan.

Tickets come after review: one per task, each with a parent, a `Gate:` line and falsifiable
criteria. Adopt an existing ticket rather than minting a duplicate.

## Known friction (from prior runs)

- **"Regenerate INDEX.md with the repository's own script" named no script,** and the registry's
  header comment points at a nonexistent `beta/plans/_engine/regenerate_plan_index.py`. The script
  is `scripts/check_plan_index.py --write` (section 0). Fixed 2026-09-23 by the omni-skill-fixes pass,
  OMN-19230 lineage.
- **The model-before-build ruling was cited by a ledger line number,** which a roll renumbers. It is
  now cited by its row timestamp and lane. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230
  lineage.
