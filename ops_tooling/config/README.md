# Workspace configuration

This repository owns the registry's private machine configuration (OMN-19743).
`lab/` holds the pre-push placement overlays. `onex/runtime/runtime_config.yaml`
declares the registry's shared bus lane. Both are private operator data; the
runtime package ships the resolver and schema, without these lab values.

Readers select `ONEX_WORKSPACE_CONFIG_ROOT` when set, otherwise the sibling
`$registry_root/../ops_tooling_pkg` repository. This also resolves to this repository
when `registry_root` names the new registry root. No reader falls back to the retiring
registry's `config/` directory.

The runtime materializer reads this repository's `origin/main` git objects and
writes YAML plus repository, reference, path, commit and timestamp attribution
under the bound workspace's `.onex_state/workspace-runtime/runtime/`. It leaves
the source index and working tree alone. The resolver rejects materialized copies
attributed to another owner, then reads this owner's working-tree config if no
attributable copy exists. A bound workspace with neither is refused.

The remote-lane runner checks this config location on the selected lab host and
provisions it there only when absent. Existing files are left intact. Developer
onboarding uses an explicit config root under its workspace's
`.onex/workspace-config/` and declares an in-memory bus there; it does not copy
the registry's lab configuration.

The overlays supply placement paths, never authorization or transport targets.
The committed host identity table and destination host checks remain authoritative.
omnibase_core's host table is the exception to the placement-only rule
(OMN-20939): `lab/prepush_hosts.omnibase_core.tsv` holds the full thirteen-column
lab rows that core no longer ships, and the core hook reads it through this
resolver, from the committed copy when this repository is a git checkout.
The older `lab/prepush_hosts.omnibase_core.overlay.tsv` placement overlay is
retained as operator data; core reads only the full table.

`vocabularies/` also holds the detector denylists of our dead endpoints that
omnibase_core's checkers read when present: `hardcoded_model_config_lab_denylist.yaml`
and `decommissioned_patterns.lab.conf`. Without them the checkers run their
shipped shape rules.

The onex/overlays/ directory contains node-specific deployment overlays that supply the deployment facts no longer carried in the source of omnimarket's hosted copies of the lab-fill selection and lab disk hygiene nodes. The lab-fill selection overlay specifies the companion repository, the not-work repository, and the document repositories, while the disk hygiene overlay specifies the lane census path relative to registry_root. These values equal the constants in this repository's own unchanged copies of the two nodes. A reader names the root directory in ONEX_SKILL_OVERLAY_ROOTS, or points the disk hygiene node at its file with OMNIMARKET_LAB_DISK_HYGIENE_OVERLAY. The lab-fill selection node is a pure compute node, so its caller reads its file and passes the parsed mapping in the request.

`onex/overlays/node_review_voters_overlay_compute/overlay.yaml` is our lab's Hostile Reviewer voter
roster (a `review_voters_overlay.v1` document, OMN-20923). The shipped repositories carry only the
schema and resolver (omniintelligence) and a neutral default; their Hostile Reviewer workflows fetch
this file at run time from the repository the org Actions variable `OMNI_CI_OVERLAY_REPO` names.

`onex/overlays/branch_protection_audit/overlay.yaml` is the fleet our branch-protection audit covers (a
`branch_protection_audit_overlay.v1` document, OMN-20955). The shipped auditor
(`src/ops_tooling_pkg/handlers/branch_protection_audit/handler_audit_branch_protection.sh` in this repository) carries a neutral default of public repositories
and the schema validator. It runs from `.github/workflows/branch-protection-audit.yml` here, on a schedule
and on every pull request that changes it, and points `BRANCH_PROTECTION_AUDIT_OVERLAY` at this file in the
same checkout. The registry workspace's branch-protection guard and gap-detect workflows fetch this
repository at a pinned commit and point the variable at the same file. Each list in the file replaces the
matching default; a key left out keeps the default.

The review_pairing and node_navigation_history_reducer overlays carry the lab endpoints that omniintelligence's review model registry and omnimemory's runtime plugin shipped as defaults until OMN-20936. The first maps a model key to its endpoint (`default_urls`), the second names the embedding endpoint (`embedding_url`). Both shipped readers find them through ONEX_SKILL_OVERLAY_ROOTS, and each model's own environment variable (or LLM_EMBEDDING_URL) still takes precedence.

The lab/ hook tables (OMN-20937) are the lab hosts omniclaude's hooks no longer carry: `hook_edge_lane.yaml` (the hook edge's lane broker table), `dispatch_claim_hosts.yaml` (hosts the dispatch claim gate treats as single-claimant), `gap_legacy_denylist.yaml` (the gap skill's lab legacy pattern) and `code_graph_query.yaml` (the embedding service the code graph query dials). Each is read from `<workspace config root>/config/lab/`. A fork with no such file gets a neutral behaviour that names the missing file.

`lab/lane-overlays/` holds our lab's lane overlays (OMN-20932): the per-lane Bifrost delegation
overlays (`<lane>.bifrost.yaml`, `bifrost_lane_overlay.v3`) and the `dev.rsd-*` overlays, moved
from omnibase_infra `docker/lane-overlays/` with identical parsed content (only the public hygiene
gate's seven `onex-allow-internal-ip` comment lines were dropped). omnibase_infra ships only the
typed schema, the renderer and the neutral `local.bifrost.example.yaml`. Its lane compose files
mount `${ONEX_LANE_OVERLAY_DIR}/${COMPOSE_PROJECT_NAME}.bifrost.yaml` at one lane-neutral path, so
each compose project our lab runs (`omnibase-infra`, `omnibase-infra-<lane>`) is a relative link
here to the lane overlay it mounted before the move. The deploy paths set `ONEX_LANE_OVERLAY_DIR`
to `config/lab/lane-overlays` under `ONEX_WORKSPACE_CONFIG_ROOT`, or under this repository when
it is the workspace's sibling, and compose refuses when the directory or the project's file is
absent. `tests/test_lane_overlays_private.py` renders every Bifrost overlay through
omnibase_infra's renderer against omnimarket's shipped base contract and checks every project link.

`lab/lane-census/` holds our lab's lane census (OMN-20934): `lane-manifest.yaml`, the
desired-state declaration of every runtime lane, its hosts, compose projects, networks and
services, and `census-snapshot.json`, the last committed census of the lab host. Both moved
from omnibase_infra `deploy/lane-census/` (the manifest with identical parsed content, less the
public hygiene gate's one `onex-allow-internal-ip` comment marker; the snapshot byte-identical).
omnibase_infra's census planner, its staleness, drift and env-drift checkers, the CLAUDE.md lane
block generator, the lab alarm and the desired-state renderer read them from
`config/lab/lane-census` under `ONEX_WORKSPACE_CONFIG_ROOT`, else the runtime's resolver for
`registry_root`, and refuse without them. Its lane census installer writes that root into the unit it
installs. Its `lane-census-refresh.yml` opens the snapshot bump pull request here (the
repository named by the org Actions variable `OMNI_CI_OVERLAY_REPO`), and its
`lane-census-parity.yml` runs the tests that cross-check its compose files and tools against this
manifest. `tests/test_lane_census_private.py` checks the pair agrees with itself.

`lab/developer-principal-overlay.yaml` is the lab dev lane's `developer.principal` overlay document (a
`developer_principal.v1` document of omnibase_core, OMN-19975). Each row names a developer machine's broker
principal, the login that holds it and its device. The document has no grant field: the grants of every
principal are derived from the infrastructure repository's `deploy/lab/developer-principal-grants.yaml`
(its `grants_source`). The lab hosts' lane logins are not rows; `src/ops_tooling_pkg/lab_broker_acls/dev_lane_acls.yaml`
holds them. `tests/test_lab_developer_principal_overlay.py` checks the document against the schema's rules.
