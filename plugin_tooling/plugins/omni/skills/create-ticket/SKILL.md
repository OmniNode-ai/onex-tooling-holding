---
name: create-ticket
description: Create one Linear ticket that the OMN-17942 create gate accepts on the first try. Decide whether it should be a ticket at all, search for duplicates, pick the owning parent (never a project, since new tickets go to the Backlog), write the Gate line, the labelled criteria with falsifiers and (for In Progress) the Probe line, then run the gate's own checker over the payload locally before the MCP call. Use whenever a lane is about to mint a ticket, including children of a plan or epic.
prosthetic: true
replaces_when: "`onex skill create_ticket` (node_create_ticket) creates through the same admission rules as the MCP gate and sets a project, on three consecutive creates. On 2026-09-23 its handler posted issueCreate straight to Linear GraphQL with teamId, title, description and parentId only: no project, and none of the OMN-17942 rules, because that gate is a PreToolUse hook on the MCP save_issue tool and never sees the node's call (ledger row 2026-09-23T06:17:07Z lane=restore-create-ticket existing=OMN-17120)."
restored_from: "omniclaude b94357001 plugins/onex/skills/create_ticket/SKILL.md (872 lines; the plugin copy is now a 72-line dispatch shim)"
ticket: OMN-19226
---

# Create ticket (prosthetic)

Agent-posted Linear comments have `actor: <lane> (<model>)` as the first line.
Lane and model come from the actual execution identity, never the Linear account author.
Every posting recipe, comment body file and `save_comment` or `create_comment` body carries
that line before the comment text. Human operator comments without an actor line remain
human even when they share the account used by an agent.

The authority is the gate's code, not this file. This file transcribes it as of omniclaude
`origin/dev` `a58fb5ea` (2026-09-23). Re-checked at `a3160b716` the same day:
`git diff --stat a58fb5ea origin/dev` over the checker, the policy and the grammar was empty. If a refusal disagrees with what is written here, the refusal
is right, and this skill needs a Known-friction line.

- checker: `omniclaude/plugins/onex/hooks/lib/ticket_creation_guard.py`
- policy (vocabulary): `omniclaude/plugins/onex/hooks/config/ticket_creation_policy.json`
- binding grammar: `omniclaude/plugins/onex/hooks/config/gate_binding_grammar.json`
- hook: `pre_tool_use_ticket_creation_gate.sh`, matched on `mcp__linear-server__(save_issue|update_issue)`,
  under the `LINEAR_DONE_VERIFY` mask bit

## 0. Should this be a ticket?

- **A residual, follow-up, nit or cleanup of other work goes as a comment on its parent,** not a new
  ticket. The gate refuses such titles (rule 4). The one exception is a live gate that is broken.
- **Friction files a ticket on its SECOND occurrence.** The first occurrence is a FRICTION row (see
  the `friction-record` skill, `/omni:friction-record`). On the second, file a ticket, or cite the one that owns the class.
- **Work another ticket already scopes gets that ticket adopted.** A lane handed work that another
  ticket scoped OUT needs its own ticket BEFORE it opens the PR (see step 7).
- **Minting needs authority.** If your brief grants none, name the ticket you would file in your
  TERMINAL row and say who owns filing it. Do not file it anyway.

## 1. Search for duplicates, then re-probe what you find

Run at least two phrasings: a distinctive noun phrase, and the file, workflow or symbol name.
Include Done and Canceled tickets. A canceled duplicate is a ruling, not a gap.

```
list_issues(query="<distinctive phrase>", limit=20, fields=["title","status","parentId","project","createdAt"])
list_issues(query="<file or symbol name>", limit=20, fields=[...])
list_issues(parentId="<intended parent>", limit=100, fields=["title","status"])   # siblings
```

Read the body of every close match. Then **re-probe its premise live** before you adopt it or file
beside it. On 2026-09-23 a brief said a defect had not been filed yet. The search found OMN-19168, and
a live read showed its premise ("fails red on every PR event") was false: the workflow had been
disabled since May (ledger row 2026-09-23T06:17:07Z lane=restore-create-ticket existing=OMN-19168). The remedy for a close match is to adopt it, or to comment the
correction on it. Never file a second ticket beside it.

For PR history use `gh search prs --merged ...`. `--state merged` is not a valid value and returns
empty (ledger row 2026-09-18T06:52:05Z lane=plan-reconcile-2026-09-18). Prove a zero with a positive control (rule 16).

## 2. Parent, no project, milestone, labels

**Parent (rule 1).** `parentId` is required, unless the body declares an epic with the line
`issue_class: epic` on its own (exact, lowercase after trimming. `Epic: OMN-n` names a parent and
does not count). Choose the parent whose SUBJECT owns the work. Reparenting to duck a refusal is the
abuse the gate exists to stop (ledger row 2026-09-19T15:07:38Z lane=omn18826-worktree-remove-stderr-fix-1405).

**No child cap.** The unstarted-children cap (rule 8, OMN-18323, N=10) was **rescinded by the
operator on 2026-09-21** ("that's not something I made", ledger row 2026-09-21T14:46:45Z lane=foreground-orchestrator ("operator rulings 2026-09-21 ~14:45Z") item f) and removed by
omniclaude#2296. A `parents_over_cap` line in `beta/GOAL.md` is a stale report from a morning run on a
lagging tree (ledger row 2026-09-23T06:17:08Z lane=restore-create-ticket, OMN-19212). It is not a gate. A crowded parent is a prompt to look harder
for a child to adopt in step 1, and nothing more. If the hook still refuses with
`unstarted_children_cap`, the plugin clone the hook loads from is stale. Report it (step 5). Never
reparent to get round it.

**No project (rule 2, inverted 2026-09-30).** Operator ruling 2026-09-30T14:30:05Z (ledger RULING
lane=orchestrator-0c2f ticket=OMN-17427): "all new tickets need to go into the backlong not into a
project." Every new ticket is created in state `Backlog` with `project` and `projectId` UNSET. The
gate now REFUSES a create that sets either (code `project_set`, naming this ruling). A parent epic
link is fine. Moving a ticket into a sprint project is the operator's call, made later by an update,
never at creation. There are no cycles.

**Milestone and C-labels.** M4 is defined by the Beta Release Board data file
(`infra_repo/tools/beta_board/beta_board_data.py`), not by Linear. Since the 2026-09-22 rescope,
Linear carries matching milestones on the sprint project: `M4 — Delegation and customer pass proven`
(C11-C17, C28, local delegation) and `M4.5 — Cloud delegation (fast follow)` (C8-C10). Label names
are `C<n>`. Set `milestone` and add the `C<n>` label **only** when the ticket carries that criterion
in the data file's bucket. A ticket outside the carriers is not M4 work, whatever it is labelled.
Resolve names with `list_milestones(project=...)` and `list_issue_labels(name="C11")`.

**blockedBy.** A foundation-repo ticket (compat, core, spi, infra) may not be blocked by an
application-repo ticket (rule 7 layering; `omniclaude/plugins/onex/lib/dependency_validator.md`).

**Lane-created items (rules 11-14, OMN-17942).** Every create a lane, a node or a workflow subagent
makes is written through the operator's one Linear key, so the item itself has to carry the fact that
a lane opened it. Two of the four rules are yours to satisfy at authoring time, and both read their
vocabulary from the `lane_intake` object of `ticket_creation_policy.json`, never from this file:

- rule 12, the label: pass `labels` including `lane_intake.label` (`lane-created`), beside whatever
  `C<n>` label this step decides. A refusal names it `lane_label_missing`.
- rule 13, the stamp: the description's FIRST line is exactly `<lane_intake.stamp_prefix> <lane>`
  (`created-by-lane: <lane>`), on its own, above the Gate line (step 6's template). The lane is your
  own declared `ONEX_LANE`, or, for a workflow subagent, the lane its harness sidecar names while
  that lane holds an open CLAIM. A refusal names it `lane_stamp_missing`.

Read the two values rather than transcribing them, so a policy change cannot leave this skill stale:

```bash
python3 -c 'import json,sys; p=json.load(open(sys.argv[1]))["lane_intake"]; print(p["label"], p["stamp_prefix"])' \
  "$registry_root/omniclaude/plugins/onex/hooks/config/ticket_creation_policy.json"
```

Rules 11 and 14 are not authoring choices: rule 11 is the lane identity the context declares (step 7
makes the pre-flight see it), and rule 14 is the day's intake budget.

**Plan-backed creates (rule 14a, RULING 2026-10-29T10:59:39Z, OMN-17942).** A ticket that is a task of an
approved plan, a plan file already at `origin/main` of the docs_repo clone, is exempt from the
day's budget and spends none of it. Cite the plan on a line of its own in the description, directly under the
Gate line of step 6's template (the template itself carries no such line, so a lane-invented ticket can never copy one): `Plan task: <plan path> <task id>`, for example
`Plan task: beta/plans/2026-10-28-validators-to-core-and-hardcoded-rules.md T0.3`. The guard reads that file at
`origin/main` of the clone `lane_intake.plan_task_exemption.clone_env` names (no network call) and admits the
create only if the id opens a task line in it (a heading, a bold token or a bold list item; prose and fenced
text do not count). Read the line's exact spelling from `lane_intake.plan_task_exemption.citation_line_pattern`
rather than transcribing it. A plan that is still on an unmerged branch, a path that is not there, or a task id
that is not in the file is refused `plan_citation_unverified` with the missing piece named; fix the citation,
and drop the line only for a ticket the lane itself invented, which spends the budget. The label and the stamp
are still required on a plan-backed create. The step 7 pre-flight needs the clone variable in its environment
too, or it refuses the citation for want of a clone.

## 3. The Gate line (rule 3)

One line of its own, **unbulleted, unbolded, not quoted**. The authoring pattern is
`^[ \t]*Gate:[ \t]*<binding>$`. `* Gate:`, `> Gate:`, `**Gate**:` and `Gate probe:` all fail at
creation, although the closer would read them later. The binding must be exactly one of these forms:

| form | spelling | notes |
|---|---|---|
| parent_criterion | `Gate: OMN-16729 AC-5` | both halves. A bare `OMN-n` is a link, not a binding. Exempts rule 10. The gate does not check that the parent has that AC, so check it yourself |
| workflow_run | `Gate: OmniNode-ai/omnibase_infra chain-canary.yml` | owner/repo plus the file. A bare filename is refused. This is the only form the closer can probe |
| release_criterion | `Gate: C11` | must be in the pinned set C1-C28 (PRD at `91d8d837`) |
| invariant | `Gate: INV-103` | at least three digits (`INV-12` is refused). Must be one of the 43 ids in the policy's `invariant_ids` |
| live_gate_defect | `Gate: live-gate defect: kb-doc-gate` | name the broken check. The only form that exempts a residual-shaped title |

Linear rewrites `OMN-n` into an `<issue>` element and editors auto-link. The grammar undoes both,
so either spelling works. **Never invent a C or INV binding you cannot defend.** Use the owning
parent's AC instead. A lane that could not do that filed nothing (ledger row 2026-09-20T11:18:15Z lane=comms-and-codex-notes-1125). That is the correct
outcome, not a failure.

## 4. Acceptance criteria (rules 6, 7, 10)

Self-contained build and fix drafts use Codex first (operator ruling 2026-09-30, OMN-20106; the plan period ends about 2026-10-30), then the lab agent, then GLM; the lane verifies. Run `delegation_step.py code` in the lane's own worktree; it keeps the `lab_crush.py` route and then one GLM draft through Claude Code (`/omni:harness-delegate --harness claude-glm --writable-repo <worktree>`). GLM runs only through Claude Code: the Coding Plan terms bar direct API calls, so the cloud-glm backend pin of `onex delegate` is retired and always fails (omnimarket#3136, OMN-20173). Never pass a model flag to Codex. The Claude lane reads every diff, runs focused tests and owns the PR. Pure text stays lab first, then GLM through Claude Code (`delegation_step.py text`); typed decisions go to Jev.

- Open the section with a recognised heading: `## Acceptance criteria`, `## Acceptance`,
  `## Definition of done`, `## DoD`, `## AC` (`### 3. Acceptance criteria:` and a trailing
  parenthetical also parse). The section runs until the next `#` heading.
- Each criterion is a list item (`-`, `*`, `+`, `1.`) or a bare `AC<n>` line. Write **each one on a
  single line**: `- [ ] AC<n>: <criterion> -- falsifier: <check name or command shape>`.
  Linear backslash-escapes a wrapped line that starts with `--`, which moves the criterion hash and
  silently withholds acceptance later (OMN-18667).
- **Every** item needs `falsifier:` (or `falsified by`) inside it. The last marker in an item wins.
  A falsifier belongs to its own item only.
- **At least one** item carries an `AC<n>` or `DOD<n>` label (a suffix is allowed: `AC2b`), unless
  the ticket is an epic or the Gate is parent_criterion. Label all of them anyway: the closer binds
  evidence by label.
- The falsifier is the check that WOULD settle the criterion, written before anything is built. It
  is never a result.
- **An incident ticket** (a fix or a tool that passed its own tests and then broke the fleet) carries a labelled criterion for
  its regression test, closed only with that evidence (RULING 2026-10-17T09:03:06Z): `- [ ] AC<n>: a regression test built from the
  incident's recorded data (fixture path) fails on the broken code and passes on the fix -- falsifier: <pytest command>`. The data is
  recorded probe output, watcher state, a tick line, rendered file text or ledger rows, scrubbed of secrets, never values the author
  imagined; the test lives in the repository that owns the code.
- **Rule 7:** a criterion is behaviour-shaped when it uses words like test(s), red-first, fails today,
  refuse(s), raise(s), retry, stops after, handler or suite, and no state words such as returns,
  contains, is running/enabled, readback, digest, HTTP nnn, or `N rows`. A behaviour-shaped criterion
  may not take a merge-state falsifier (`gh pr`, `gh run`, `git log/show/rev-parse`, "PR is merged",
  "CI green", "squash sha") **unless the falsifier also names a runner** (pytest, tox, vitest, jest,
  onex, ...). `gh api repos/O/r/commits/<sha> --jq .sha && uv run pytest tests/x -q` passes both rules.
- The falsifier sits inside the criterion's hash. Get it right now: an UPDATE may not rewrite a
  criterion's line (rule 9, OMN-18404). Put evidence in a comment, or on an indented line below the
  criterion.

## 5. The Probe line (rule 5, only when the create sets an In Progress state)

If `state` is `In Progress`, `in-progress`, `started` or similar, add one unbulleted line of its own:
`Probe: <command> => <observation a machine can compare>`. Both halves are required. A ticket parked
in Backlog is not checked for this, but writing the line anyway costs nothing.

## 6. Template

```markdown
created-by-lane: <lane>

Gate: OMN-<parent> AC-<n>

Probe: <command> => <observable result>

<Two to five sentences: what is wrong or missing, where (repo, file:line, run id, ledger row timestamp and lane), and
the evidence, read live. Who asked for it, as a role ("operator ruling 2026-09-23"), never a name.>

## Acceptance criteria

- [ ] AC1: <state or behaviour that settles it> -- falsifier: <command shape or check name>
- [ ] AC2: <...> -- falsifier: <...>
```

The first line is the lane stamp of rule 13 (step 2): exactly `<lane_intake.stamp_prefix> <lane>` —
`created-by-lane: <lane>` with the policy's current prefix — followed by a blank line, then the Gate
line. A create a person makes interactively carries no lane context, so it opens at the Gate line and
drops the stamp; everything a lane, a node or a workflow subagent opens keeps it. The stamp goes with
the `lane_intake.label` (`lane-created`) in `labels`: the two rules fail separately, and a body with
the stamp and no label is still refused `lane_label_missing`.

MCP arguments: `team="Omninode"`, `title` (no follow-up/residual/nit/minor/cleanup/noted wording),
`description`, `parentId`, plus `state` (leave it at `Backlog`; do NOT pass `project`, the gate refuses the string `null` and a blank one does not clear anything; step 8 clears the project afterwards with an update that carries the JSON null), `assignee` (by pillar, see below), `priority`, `milestone` and
`labels` as step 2 decides, including `lane-created` for a lane create. **Do not pass `template`.**
The gate cannot see a body that Linear fills
in on its side, so it refuses the create as unevaluable.

**Assignee by pillar** (operator ruling 2026-09-30, lane orchestrator-0c2f, OMN-17427). Anything that deals with the
dashboard, including the data layer behind it (projection API, projection writers and exposures that feed it, unfed
dashboard topics, widgets, pages), gets the dashboard pillar's owner. Onboarding (install paths, bootstrap and
setup, first-run and marketplace flow, minimum system requirements, the onboarding test matrix, local-install work)
gets the onboarding pillar's owner. Everything else gets `assignee="me"`. The owner is a Linear user id held in
ops_tooling_pkg's `pillar_owners.yaml`, not in an environment variable: run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_pillar_owner.py" dashboard` (or `onboarding`) and pass its one line of
output as `assignee`. When the pillar applies and the command exits non-zero, stop and say so, never fall back to
`me`. A new ticket still goes to Backlog with no
project unless the operator names a sprint for that ticket; the operator's 2026-09-30 bus-identity ticket is the one
dated exception. When a ticket touches both pillars, the dashboard pillar wins, and the description says so.

## 7. Pre-flight: run the gate's own checker locally

Write the exact `tool_input` you will send, wrapped as a hook payload, with the editor tool (not a
heredoc, which the scope gate refuses when the body holds an apostrophe; ledger row 2026-09-23T01:03:54Z lane=friction-to-skills):

```json
{"tool_name": "mcp__linear-server__save_issue",
 "agent_id": "<this subagent's agent id>",
 "session_id": "<this session's id>",
 "transcript_path": "<.../agent-<agent id>.jsonl>",
 "tool_input": {"team": "Omninode", "title": "...", "description": "...",
                "parentId": "OMN-...", "state": "Backlog",
                "labels": ["lane-created"]}}
```

**The payload carries the caller's identity, not just the tool call.** The harness sends
`agent_id`, `session_id` and `transcript_path` to the real hook, and the lane-intake rules (11-14)
are reached only through them: `handler_lane_intake.begin` returns no admission at all for a payload
with no `agent_id` when the environment declares no `ONEX_LANE` and the entrypoint is not headless,
so rules 11-14 are never judged and the pre-flight exits 0 on a create the live hook then refuses
`lane_label_missing` and `lane_stamp_missing` (seventeen payloads at FRICTION 2026-10-21T20:29:31Z
lane=ruling-mechanisms-2015, one at FRICTION 2026-10-21T18:57:57Z lane=landing-hook-env-1845;
OMN-21270). A pre-flight whose payload omits them is testing a different create from the one you are
about to make.

- **A workflow subagent** takes all three from its own harness context: `transcript_path` is its
  `agent-<agent id>.jsonl` under the session's project transcript directory, `agent_id` is that
  file's `<agent id>`, and `session_id` is the parent session's id. The sidecar
  `agent-<agent id>.meta.json` beside that transcript is what names the lane, and it counts only
  while that lane holds an open CLAIM on the rolling work ledger — so append the CLAIM before the
  pre-flight, not after. Without the CLAIM the refusal is `lane_identity_missing`, which names the
  lane the sidecar claimed.
- **A lane that declares `ONEX_LANE`** (or `ONEX_REMOTE_LANE`) needs no `agent_id`: the environment
  the pre-flight inherits names the lane, and rules 11-14 are judged from it. Run the pre-flight in
  that same environment, never with the variable stripped.
- **A person, interactively**, is not in a lane context and the rules do not apply. Leave the three
  identity fields out, and leave the label and the stamp out with them.

```bash
G="$registry_root/omniclaude/plugins/onex/hooks/lib/ticket_creation_guard.py"
python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh OmniNode-ai/omniclaude --wait   # not a git fetch (OMN-20495)
git -C "$registry_root/omniclaude" diff --stat HEAD origin/dev -- plugins/onex/hooks/lib/ticket_creation_guard.py \
  plugins/onex/hooks/config/ticket_creation_policy.json plugins/onex/hooks/config/gate_binding_grammar.json
env -u PYTHONPATH /opt/homebrew/bin/python3.13 "$G" < payload.json; echo "exit=$?"
```

- `exit=0` admits the create. `exit=3` refuses it: the reason is JSON on stdout, naming **every**
  failing rule with a fix. `exit=1` means the guard could not decide, and the hook treats that as a
  refusal.
- The diff names exactly the three files the checker reads: the guard itself (it imports nothing
  else from the repo), its policy and the Gate binding grammar. An empty `diff --stat` means the local
  copy is what `origin/dev` ships. If it is not empty, the hook is running an older checker. Pre-flight against both copies, and report the lag. Do not sync a
  canonical clone or reinstall the plugin as a side effect.
- `ONEX_STATE_DIR` must be set to an absolute, readable directory, or rule 14 cannot be measured and
  the refusal is `unevaluable` on `lane_intake`.
- **Positive control:** delete the Gate line and re-run. It must exit 3 with `missing_gate_line`. A
  pre-flight that cannot refuse proves nothing.
- **Second positive control, for the lane rules:** drop the `lane-created` label and the
  `created-by-lane:` first line from the same payload and re-run. It must exit 3 naming both
  `lane_label_missing` and `lane_stamp_missing`. A pre-flight that still exits 0 is one whose payload
  carries no identity, which is the OMN-21270 defect: fix the payload, not the body.

## 8. Create, read it back, attach work to it

1. Call `mcp__linear-server__save_issue` with the same arguments. **Never use `onex skill create_ticket`.**
   Its node calls Linear directly, never passes the gate, and cannot set a project (ledger row 2026-09-23T06:17:07Z lane=restore-create-ticket existing=OMN-17120).
2. **Clear the project the create inherited, with a JSON null.** Linear copies a parent's project onto a sub-issue created without one, so a child of a parent in project Ready comes out in Ready (OMN-21723; OMN-22358, OMN-22359 and OMN-22363 on 2026-11-03). Straight after the create, call `save_issue(id=<new id>, project=null)` as an update, never the create (the create gate refuses a set project). The value is the JSON `null` literal, the tool's own "Null to remove". **It is not the string `"null"`, not `"None"` and not an empty string:** the tool reads each of those as a project name or a blank and leaves the project where it is (the three tickets above sat in Ready because their lanes passed the string `"null"`; verified with a JSON null on all three at 2026-11-03T15:01Z). Do not skip the call because the create looked clean: it costs one update and the copy is silent.
   Then `get_issue(id)` and **verify the project is empty** (no `project`, no `projectId`). If it is not, repeat the update with the JSON null and read it back until it is empty; a lane that cannot get it empty reports that in its TERMINAL row and never leaves the ticket in a sprint project. Also check the state is Backlog, the parent and the milestone, and that the Gate line survived.
   Linear wraps it in an `<issue>` element, which is fine.
3. **The PR title carries the new id.** Linear attaches a PR to the id in its TITLE. A PR titled with
   the id of the ticket that handed you the work attaches there, and it can then close that ticket
   on evidence that does not satisfy it. To fix that, retitle the PR (this works after merge too),
   delete the old attachment explicitly, and read the old ticket back to confirm it is gone.
4. Append to a description with a blank line before a horizontal rule (`\n\n---`). A bare `\n---\n`
   directly under a paragraph turns that paragraph into a heading.
5. Ledger: cite the id in your CLAIM or TERMINAL row. Any refused create is a FRICTION row.

## 9. On a lab host: no Linear tool, so `onex ticket` over the bus

A headless lab lane has no `mcp__linear-server__save_issue`, so steps 7 and 8 do not run there. The route
for it is the Linear node in the dev runtime: `onex ticket create` publishes the request on the bus, the
node runs the same create gate (the guard of steps 2 to 6, as a lane create) next to the Linear key, and the
terminal carries the new id. The lane never holds, prints or passes a key. Steps 0 to 6 are unchanged: the
same parent, no project, Gate line, criteria with falsifiers, `created-by-lane: <lane>` first line. The node
adds the `lane-created` label itself, creates in Backlog, and clears the project a parent copied onto the
child, so none of those is an argument.

Write the description with the editor tool into a file, then dry run, then create. The config root is the
one the lane runner exports (`ONEX_WORKSPACE_CONFIG_ROOT`); the bus lane is `dev`.

```bash
onex ticket create --lane "$ONEX_LANE" --bus-lane dev --dry-run \
  --title "<title>" --parent OMN-<n> --description-file <file>
onex ticket create --lane "$ONEX_LANE" --bus-lane dev --idempotency-key "<lane>-<slug>" \
  --title "<title>" --parent OMN-<n> --description-file <file>
```

- **The dry run is the step 7 pre-flight.** It runs the real guard on the exact payload and makes no Linear
  write: `failed` with reason `guard_refused` and the guard's finding codes (`missing_gate_line`,
  `lane_stamp_missing`, an unfalsified criterion) names every rule to fix in one pass, as the hook's refusal
  does. Positive control: delete the Gate line from the file and the dry run must end `guard_refused` with
  `missing_gate_line`.
- **The id is in the terminal**: the command prints one JSON object and `payload.result.ticket_id` (and
  `ticket_url`) is the new ticket. Read it back with `onex ticket read <id>` and check the state, the parent
  and the Gate line, as in step 8. Use the id in the PR title.
- **Exit codes**: `0` completed, `1` a failed terminal (reason in `payload.reason`), `69` the bus could not be
  opened (nothing was sent; the JSON says why), `75` no terminal in time. An exit `75` is an unknown outcome:
  read before retrying, and retry with the same `--idempotency-key` and the same file so a create that did
  land is replayed and not made twice (the replay record lives in the node's process, so after a runtime
  restart read the parent's children first).
- **Failed terminal reasons**: `guard_refused` fix the findings; `guard_unavailable` the dev runtime holds no
  guard (a runtime defect, ticket it and cite this skill); `secret_unavailable` with
  `linear_api_key_unresolved` the dev runtime cannot resolve the Linear key (same); `invalid_request` the
  node refused the request's shape (the finding codes name the field); `operation_failed` the call failed past
  the guard (the node logs the type only); `idempotency_conflict` the same key was sent with different content.
- **Duplicate search (step 1)** has no Linear list on a lab host: search the ledger with
  `/omni:ledger-ask`, read each candidate with `onex ticket read`, and say in the TERMINAL that the
  Linear-side search could not run.
- A lane that is not on a lab host, with the MCP tool, uses steps 7 and 8, never this route.

## Guardrails

- Never disable `LINEAR_DONE_VERIFY` or route around the gate (the node path, raw GraphQL, a
  template body). Fix the payload. If the gate itself is wrong, that is a `live-gate defect` ticket.
- Never fabricate a binding, a falsifier you do not mean, or a probe you have not checked parses.
  The gate checks shape, not truth. The closer later runs what you wrote.
- Keep person names out of any ticket whose text feeds docs_repo or public docs. Use
  roles ("operator", "cloud owner"). An attributed paraphrase with a date replaces a quote.
- Never spell a trigger literal in a title or body (rule 15): no merge-hold vocabulary, skip-token
  prefixes or the evidence-source stamp line in prose. Name the family instead.
- One ticket per unit of work that one lane lands in one PR. A plan's children come from the
  `plan-write` skill (`/omni:plan-write`) after review. Never mint ahead of the plan.
- When a create is refused, read every finding and fix them all in one pass. The refusal lists all
  of them at once.

## Known friction (from prior runs)

- **Refused on four rules at once (a project set, no Gate, eight criteria without falsifiers, a crowded
  parent), then again on a merge-state falsifier:** about 25 minutes, spent mostly working out the grammar
  from JSON. Pre-flight locally (step 7). → ledger row 2026-09-19T13:11:52Z lane=claude-md-memory-dedup-review-1235, OMN-18818
- **The Gate grammar was discoverable only from the refusal text.** Steps 3 and 4 transcribe it. →
  ledger row 2026-09-21T08:45:50Z lane=friction-adjudicate-2026-09-21, OMN-18174
- **A lane declined to invent a C or INV binding and so filed nothing.** That was correct. Bind to the
  owning parent's AC instead. → ledger row 2026-09-20T11:18:15Z lane=comms-and-codex-notes-1125
- **Unstarted-children cap refusals (ledger rows 2026-09-18T23:06:47Z lane=remediation-plans-rereview-2235; 2026-09-18T23:33:15Z lane=validation-silent-paths-inventory-2230; 2026-09-18T23:37:41Z lane=validation-silent-paths-inventory-2230; 2026-09-19T15:07:38Z lane=omn18826-worktree-remove-stderr-fix-1405; 2026-09-20T16:10:48Z lane=seam-defect-prevention-plan-1540):** the cap was rescinded on
  2026-09-21. If you see `unstarted_children_cap` today, the hook clone is stale. → ledger row 2026-09-21T14:46:45Z lane=foreground-orchestrator ("operator rulings 2026-09-21 ~14:45Z"),
  ledger row 2026-09-21T15:55:00Z lane=cap-rescind, omniclaude#2296
- **`parents_over_cap` is still printed by a morning run on a lagging shared tree** and was read as a
  live cap. → ledger row 2026-09-23T06:17:08Z lane=restore-create-ticket, OMN-19212
- **The brief's suggested defect was already filed, and its premise was false.** Search, then
  re-probe. → OMN-19168, ledger row 2026-09-23T06:17:07Z lane=restore-create-ticket existing=OMN-19168
- **A child of a parent in project Ready came out in Ready** on every create: Linear copies the parent's project, the gate sees only the call, and a create carrying `project` (even `null` or blank) is refused or ignored. Clear it with `save_issue(id, project=null)` and read it back. → OMN-21723
- **Three lane-minted children (OMN-22358, OMN-22359, OMN-22363) stayed in Ready after the clearing step was written,** because the lanes passed the string `"null"`, which the tool does not read as a removal. Step 8.2 now names the JSON `null` literal, forbids the string, and makes the update and the empty-project readback unconditional. → OMN-22363, ledger row 2026-11-03T15:00:27Z lane=handoff-deadlock-1445
- **`onex skill create_ticket` bypasses the create gate and sets no project.** → OMN-17120, ledger
  row 2026-09-23T06:17:07Z lane=restore-create-ticket existing=OMN-17120
- **A wrapped `--` in a criterion is escaped by Linear, which moves the AC hash.** Keep each
  criterion on one line. → OMN-18667
- **An epic create was refused because two of six criteria had no falsifier.** Write the falsifier in
  the same act as the criterion. → ledger row 2026-09-20T16:10:48Z lane=seam-defect-prevention-plan-1540
- **`gh search prs --state merged` returns empty and looks like a clean zero.** Use `--merged`. →
  ledger row 2026-09-18T06:52:05Z lane=plan-reconcile-2026-09-18
- **A heredoc containing an apostrophe is refused by the scope gate.** Write payload and body files
  with the editor tool. → ledger row 2026-09-23T01:03:54Z lane=friction-to-skills, OMN-19019
- **A PR titled with the handing-off ticket's id attached there and blocked its close.** Mint your own
  ticket first. → memory reference_pr_title_ticket_id_drives_linear_attachment
- **First-try admission of this skill's own ticket, built from step 6 and pre-flighted in step 7:**
  OMN-19226, admitted with zero refusals at 2026-09-23T06:15Z.
- **Every `ledger:NNNN` pointer in this skill went dead when the ledger rolled** at
  2026-09-23T14:00:47Z. Each one now names its row by timestamp and lane (plus a type, an `item=`,
  an `existing=` or a quoted phrase where two rows share both). Find a row with
  `grep -hF '<timestamp>' $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md $registry_root/docs/tracking/archive/*-split.md`.
  Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **The step-7 lag check diffed the whole hooks `config/` directory,** so two unrelated guard
  policies that changed on `origin/dev` (the git-stash and shared-tree guard policies) raised a
  false "older checker" alarm. It now diffs only the guard, `ticket_creation_policy.json` and
  `gate_binding_grammar.json`, after a fetch. Fixed 2026-09-23 by the omni-skill-fixes pass,
  OMN-19230 lineage.
