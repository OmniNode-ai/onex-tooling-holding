---
name: delegation-judge
description: "Judge delegated output blind and write the model by task type matrix of true accept rate beside terminal_ok. Takes a corpus of delegated tasks and outputs, has a Codex judge (high effort, the model in Codex's own config) judge every item, has Opus re-judge a seeded 10 percent sample, and fails the run loud when Cohen kappa between the two is under 0.6 or the sample is under 10 percent. The rubric, the judge prompt, the reply check, the agreement gate, the Wilson intervals and the matrix are omnimarket's node_delegation_acceptance_judge_compute (rubric v1), run with onex node; this skill only moves files and calls the judges through harness-delegate. The report goes to docs_repo reports/delegation-evals/. Use when someone asks how often a delegate's output is actually usable, before changing routing on terminal_ok, and to re-measure a model or task type after a change."
prosthetic: true
replaces_when: "A node on the bus runs the acceptance judge on a schedule and a projection folds its verdicts into capability_scores that the routing policy engine reads (OMN-20428), on two consecutive weeks of routing decisions that name the judged accept rate."
restored_from: "none: new skill (OMN-20429), from the first calibrated run of OMN-20422"
ticket: OMN-20429
argument-hint: "<corpus.jsonl> <events.jsonl> [primary codex|opus] [secondary opus|codex]"
---

# Delegation judge (prosthetic)

`terminal_ok` says a delegation ended without an error. It does not say the output was usable. In the
first calibrated run it read 96 percent over 7901 events while a blind judge accepted 57 percent of the
same cells' outputs, weighted by volume. This skill repeats that measurement on demand.

**This is a measurement, not an acceptance gate.** The standing ruling that no model judge sits in the
acceptance gate is untouched: nothing here changes routing, the rendered contract or any score. Feeding
the verdicts to `capability_scores` is OMN-20428, a separate ticket.

## What lives where

| piece | where | why |
| -- | -- | -- |
| the rubric: accept criteria per task class, the permitted-reply rule (a refusal or "cannot execute" reply the task allows is an accept), invented facts as an automatic reject, probes excluded, calibration provenance | `omnimarket/src/omnimarket/configs/delegation_acceptance_judge_rubric.v1.yaml` | data beside the other delegation rubrics; a change is a v2 file, never an edit |
| prompt render, reply check, kappa gate, sample size, Wilson intervals, the matrix, the report text | `node_delegation_acceptance_judge_compute`, run by `onex node` | everything is a node; this skill is a shim and owns no logic |
| calling the judges | `/omni:harness-delegate` (a logged-in Codex or Claude Code, never an API key), with `--no-emit` so judge calls are not counted as delegations | the one sanctioned path |
| moving files between them | the run script below | glue only |

## Inputs

- `CORPUS`: JSON lines, one delegated call each: `correlation_id`, `model`, `task_type`, `prompt_text`,
  `response_text`, and optionally `kind` and `note`. Draw it from the lab `delegation_events` projection as
  the first run did: `terminal_ok` true, a non-empty answer, exact repeats removed, a seeded random order inside a
  recent window, with a few times the per-cell count per model, task type and edit-loop kind (the node
  caps each cell and drops liveness probes). The first run's draw is described under "How it was measured"
  in its report. A draw node that reads the projection is not built yet.
- `EVENTS`: JSON lines, one per real event of the same cells without its text: `model`, `task_type`,
  `prompt_head` (the first 400 characters), `prompt_chars`, `terminal_ok`. These give the cell totals and
  the `terminal_ok` columns. Set `NO_EVENTS=1` to leave those columns blank.

## Run it

Write the block below to a scratch file outside any repository and run it with bash, after setting the
variables its first lines name. It needs `jq`, `registry_root`, `DOCS_REPO_PATH` (no default), and an
`onex` that has the node: until the CLI venv carries the omnimarket release that ships it, set
`DELEGATION_JUDGE_ONEX` to the `onex` of a venv built from the omnimarket worktree.

<!-- run-script -->
```bash
# delegation-judge run script
set -euo pipefail
: "${W:?a fresh work directory outside any repository}"
: "${CORPUS:?corpus.jsonl}"
: "${SEED:?a seed so the draw and the sample reproduce}"
: "${REPORT_DIR:?the report folder under reports/delegation-evals in the docs_repo clone}"
: "${registry_root:?}"
PRIMARY="${PRIMARY:-codex}"; SECONDARY="${SECONDARY:-opus}"; PER_CELL="${PER_CELL:-18}"; TRIES="${TRIES:-3}"
ONEX="${DELEGATION_JUDGE_ONEX:-$registry_root/omnibase_infra/scripts/onex}"
RUBRIC="${RUBRIC:-$registry_root/omnimarket/src/omnimarket/configs/delegation_acceptance_judge_rubric.v1.yaml}"
HD="${DELEGATION_JUDGE_HARNESS:-${CLAUDE_PLUGIN_ROOT:?}/skills/harness-delegate/scripts/harness_delegate.py}"
[ "$PRIMARY" != "$SECONDARY" ] || { echo "primary and secondary must differ: agreement needs two judges" >&2; exit 64; }
if [ -z "${EVENTS:-}" ] && [ -z "${NO_EVENTS:-}" ]; then echo "set EVENTS=<events.jsonl>, or NO_EVENTS=1" >&2; exit 64; fi
mkdir -p "$W" "$REPORT_DIR"

# One node call: the request file in, the node's payload out. onex node exits 1 when the payload says
# status failed (a refused reply, a failed gate) and puts the payload in result.terminal_payload; any
# other exit, or a result with no payload, is an error. The two judges run at once, so each call keeps its
# own output beside its request; stderr is kept, never dropped.
node() {
  local rc=0 payload
  "$ONEX" node node_delegation_acceptance_judge_compute --input "${1}" --state-root "$W/state" \
    --output receipt > "${1}.out" 2> "${1}.err" || rc=$?
  payload=$(tail -n 1 "${1}.out" | jq -c '.result.terminal_payload // .result' 2> "${1}.jqerr") || payload=""
  if [ "$rc" -gt 1 ] || ! jq -e '.operation' <<<"$payload" > /dev/null; then
    cat "${1}.err" "${1}.jqerr" >&2; echo "onex node failed (rc=$rc) on ${1}: ${payload:0:400}" >&2; return 2
  fi
  printf '%s\n' "$payload"
}

# 1. Render: probes dropped, each cell capped, the batches and the second-judge sample chosen by the seed.
jq -c '{item_id: .correlation_id, model, task_type, kind: (.kind // ""), task_text: .prompt_text, answer_text: .response_text, note: (.note // "")}' "$CORPUS" | jq -s . > "$W/items.json"
jq -n --rawfile y "$RUBRIC" --slurpfile i "$W/items.json" --arg seed "$SEED" --argjson cap "$PER_CELL" \
  '{operation: "render", rubric_yaml: $y, seed: $seed, cell_cap: $cap, items: $i[0]}' > "$W/render.req.json"
node "$W/render.req.json" > "$W/render.json"
jq -r '"delegation-judge: \([.batches[] | select(.role == "primary")] | length) primary and \([.batches[] | select(.role == "secondary")] | length) second-judge batches; \(.excluded_probe_ids | length) probes excluded; \(.dropped_item_ids | length) over the cell cap"' "$W/render.json"

# 2. Judge: every batch through harness-delegate, every reply through the node's check, up to TRIES per batch.
# Try 1 sends the rendered prompt as it is. A refused reply is not retried blind: the next try sends the
# rendered prompt plus a correction block naming the check's own issues (code, item id, message), so the
# judge learns what was refused. The reply itself is never trimmed or rewritten here: a verdict is the
# judge's words or no verdict. Each try keeps its own prompt, harness receipt and check in the work directory.
judge() { # judge <role> <codex|opus>: appends the checked verdicts of that role's batches to verdicts.<role>.jsonl
  local role="${1}" who="${2}" id try answer prompt
  local -a who_args
  case "$who" in
    codex) who_args=(--harness codex --effort high) ;;
    opus) who_args=(--harness claude --model opus --effort high) ;;
    *) echo "unknown judge $who" >&2; return 64 ;;
  esac
  : > "$W/verdicts.$role.jsonl"
  jq -c --arg r "$role" '.batches[] | select(.role == $r)' "$W/render.json" | while IFS= read -r batch; do
    id=$(jq -r .batch_id <<<"$batch"); jq -r .prompt <<<"$batch" > "$W/$id.prompt.md"
    prompt="$W/$id.prompt.md"
    for try in $(seq 1 "$TRIES"); do
      rm -rf "$W/$id.try$try.runs"
      python3 "$HD" run --prompt-file "$prompt" --task-class reasoning --check 'test -s "$HARNESS_ANSWER_FILE"' \
        --out-dir "$W/$id.try$try.runs" --no-emit "${who_args[@]}" > "$W/$id.try$try.harness.out" 2> "$W/$id.try$try.harness.err" \
        || { cat "$W/$id.try$try.harness.err" >&2; echo "$who judge failed on $id (try $try of $TRIES)" >&2; return 4; }
      answer=$(ls "$W/$id.try$try.runs"/*/answer.md)
      jq -n --rawfile y "$RUBRIC" --rawfile r "$answer" --argjson ids "$(jq -c .item_ids <<<"$batch")" \
        '{operation: "check", rubric_yaml: $y, batch_item_ids: $ids, reply_text: $r}' > "$W/$id.try$try.check.req.json"
      node "$W/$id.try$try.check.req.json" > "$W/$id.try$try.check.json"
      if [ "$(jq -r .status "$W/$id.try$try.check.json")" = passed ]; then
        jq -c '.verdicts[]' "$W/$id.try$try.check.json" >> "$W/verdicts.$role.jsonl"; continue 2
      fi
      echo "$who reply for $id refused (try $try of $TRIES):" >&2; echo "  receipt: $W/$id.try$try.runs" >&2
      jq -r '.issues[] | "  \(.code)\(if (.item_id // "") == "" then "" else " " + .item_id end): \(.message)"' "$W/$id.try$try.check.json" >&2
      [ "$try" -lt "$TRIES" ] || break
      prompt="$W/$id.try$((try + 1)).prompt.md"
      { cat "$W/$id.prompt.md"
        printf '\n=== CORRECTION (try %s of %s) ===\n' "$((try + 1))" "$TRIES"
        printf 'Your previous reply to this prompt was refused by the reply check, for these items:\n'
        jq -r '.issues[] | "- \(.code)\(if (.item_id // "") == "" then "" else " " + .item_id end): \(.message)"' "$W/$id.try$try.check.json"
        printf 'Write the whole reply again, every item, in the format asked for above. Fix only the items listed; keep each fix within the rule it names.\n'
      } > "$prompt"
    done
    echo "batch $id was refused $TRIES times: no matrix from an unchecked judge" >&2; return 4
  done
}
judge primary "$PRIMARY" & primary_pid=$!
judge secondary "$SECONDARY" & secondary_pid=$!
wait "$primary_pid" || exit 4
wait "$secondary_pid" || exit 4

# 3. Join to receipts and events, score, write the report.
jq --slurpfile r "$W/render.json" '($r[0].batches | map(select(.role == "primary") | .item_ids) | flatten) as $kept | map(select(.item_id as $x | $kept | index($x)))' "$W/items.json" > "$W/kept.json"
jq -r '.[].item_id' "$W/kept.json" | while IFS= read -r cid; do
  kind=none
  if [ -f "$registry_root/.onex_state/runs/$cid/receipt.json" ]; then kind=onex-run
  elif [ -f "$registry_root/.onex_state/harness-delegate/$cid/receipt.json" ]; then kind=harness; fi
  jq -nc --arg i "$cid" --arg k "$kind" '{item_id: $i, receipt: $k}'
done | jq -s . > "$W/receipts.json"
jq -s . "$W/verdicts.primary.jsonl" > "$W/verdicts.primary.json"
jq -s . "$W/verdicts.secondary.jsonl" > "$W/verdicts.secondary.json"
if [ -n "${EVENTS:-}" ]; then jq -s . "$EVENTS" > "$W/events.json"; else echo '[]' > "$W/events.json"; fi
jq -n --rawfile y "$RUBRIC" --slurpfile i "$W/kept.json" --slurpfile p "$W/verdicts.primary.json" \
  --slurpfile s "$W/verdicts.secondary.json" --slurpfile e "$W/events.json" --slurpfile r "$W/receipts.json" \
  '{operation: "score", rubric_yaml: $y, items: $i[0], primary_verdicts: $p[0], secondary_verdicts: $s[0], cell_events: $e[0], receipts: $r[0]}' > "$W/score.req.json"
node "$W/score.req.json" > "$W/score.json"
jq -r .report_markdown "$W/score.json" > "$REPORT_DIR/README.md"
jq 'del(.report_markdown)' "$W/score.json" > "$REPORT_DIR/summary.json"
jq -c --slurpfile p "$W/verdicts.primary.json" --slurpfile s "$W/verdicts.secondary.json" --slurpfile r "$W/receipts.json" \
  '($p[0] | map({key: .item_id, value: .}) | from_entries) as $pm | ($s[0] | map({key: .item_id, value: .}) | from_entries) as $sm
   | ($r[0] | map({key: .item_id, value: .receipt}) | from_entries) as $rm
   | .[] | {item_id, model, task_type, kind, receipt: ($rm[.item_id] // "none"), task_chars: (.task_text | length), answer_chars: (.answer_text | length), primary: $pm[.item_id], secondary: $sm[.item_id]}' \
  "$W/kept.json" > "$REPORT_DIR/judgments.jsonl"

# 4. The gate. A failed run keeps its report, headed UNCALIBRATED, and exits 3.
if ! jq -e '.status == "passed"' "$W/score.json" > /dev/null; then
  echo "delegation-judge: GATE FAILED (report at $REPORT_DIR):" >&2
  jq -r '.issues[] | "  \(.code): \(.message)"' "$W/score.json" >&2
  exit 3
fi
echo "delegation-judge: calibrated; report at $REPORT_DIR"
```

Variables: `W`, `CORPUS`, `SEED`, `REPORT_DIR`, `EVENTS` (or `NO_EVENTS=1`); optional `PRIMARY` (default `codex`),
`SECONDARY` (default `opus`), `PER_CELL` (default 18 judged items per model, task type and kind), `TRIES`
(default 3 per batch; after a refused reply the next try's prompt is the rendered one plus a correction block
listing the check's issues). The report folder is
`$DOCS_REPO_PATH/reports/delegation-evals/<date>-judged-acceptance-matrix`.

## Exit codes

| code | meaning | what you do |
| -- | -- | -- |
| 0 | done, calibrated | read `README.md` |
| 2 | the node refused a request or was not found | the printed node error; check `DELEGATION_JUDGE_ONEX` |
| 3 | the gate failed: kappa under 0.6, a second-judge sample under 10 percent, no double-judged item, or a missing verdict | the report is written and headed **UNCALIBRATED**; do not route on it. Re-run with another seed, or read the disagreements in `judgments.jsonl` |
| 4 | a judge failed, or its reply was refused on every try | the printed defects; the work directory holds every prompt and reply |
| 64 | usage | fix the variables |

## What the report carries

`README.md` (rubric version, the agreement line, the volume-weighted accept rate beside `terminal_ok`, the
matrix, rejects by failure class), `summary.json` (the node's score result) and `judgments.jsonl` (one line
per judged item: correlation id, model, task type, kind, the receipt join, both verdicts, text lengths).
**It carries no task or answer text.** The receipt join is `onex-run` when
`$registry_root/.onex_state/runs/<correlation id>/receipt.json` exists, `harness` for
`.onex_state/harness-delegate/<correlation id>/receipt.json`, else `none`. Calls made from lab hosts keep
their receipts there, so `none` is not a defect.

Commit the report folder to docs_repo through its scrub
(`uv run --project "$registry_root/../ops_tooling_pkg" onex-shared-doc-scrub --names-file "$registry_root/../ops_tooling_pkg/vocabularies/person_names.txt" --write <paths>`), in its own pull request.

## How to read the matrix

- **Accept rate** is the share of judged outputs a competent reviewer would use as-is or after trivial
  edits, with the Wilson 95 percent interval. At 18 items a cell separates from another only at roughly 30
  points. A cell with fewer than 15 judged items is marked thin and carries no routing weight.
- **terminal_ok x accept** is the share of all calls in the cell that end with a usable answer.
- **Codex is the stricter judge.** In calibration it rejected 11 labelled-accept items to Opus's 7, mostly by
  reading explicit instructions literally. The Opus sample and the kappa gate exist to bound that.
- **The calibration agreement is a lower bound.** On 10 of the 76 calibration items both judges disagreed
  with the label, and several labels were themselves wrong; the rubric's provenance lists them.
- A task longer than 30000 characters is shortened for the judge with the omission named in a note, which is
  not a fabrication finding.

## Guardrails

- Read only: nothing here writes a row, restarts a service or touches the ledger.
- Never append `2>/dev/null` to a command in the script (CLAUDE.md rule 16): the node's and the harness's
  stderr are captured to files and printed on failure.
- Never give a judge an API key. A harness that is not logged in is refused by harness-delegate (exit 77).
- The judge is blind: the prompt carries the correlation id, the routing label and the texts, never a model name.
- Do not edit the rubric to move a number. A rubric change is a new version file and a new calibration.

## Known friction (from prior runs)

Read this before the first run. Record new friction with `/omni:friction-record` and add a line here in the
same pull request.

- **A strict most-recent draw takes 18 consecutive turns of one editing loop.** Draw seeded random inside the
  window; the node caps each model, task type and kind cell. → OMN-20422
- **Most of one model's test volume was single-word liveness probes** (225 of 276 events). The node drops them
  from judging and from the cell totals. → OMN-20422
- **The harness emitter stores only the first 4000 characters of a task**, so 13 of 289 corpus items were cut at
  the source. A sibling event carrying the same prompt in full recovered 9; pass the recovered text, and put the
  cut in `note` for the rest. → OMN-20422
- **A refused reply was retried with the same prompt**, so all three tries of every batch failed the same
  `reason_too_long` check and the second judge gave no verdict. The retry now names each refused item, its
  code and the check's message to the judge; the bound stays the rubric's. → OMN-17427
