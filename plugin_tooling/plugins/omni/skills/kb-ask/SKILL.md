---
name: kb-ask
description: Answer a question from the planning corpus (docs_repo) with citations to file path, heading and line range, taken from origin/main and never from general knowledge. Search a snapshot of origin/main with rg, rank and cap the excerpts, draft the answer on the lab delegation route, and check every citation. If nothing relevant turns up, the reply is "not in the KB" with the search terms used. Use when anyone asks what the team decided, where something is written, how a runbook says to do something, or what a plan, guide or tracking document says.
prosthetic: true
replaces_when: "omnimemory ingestion and retrieval over docs_repo is live and in scope, so that a question returns ranked, cited passages from a maintained index instead of a hand-run grep, on two consecutive weeks of real questions. On 2026-09-23 omnimemory was ruled out of scope for now and a quick tool was asked for instead."
restored_from: "none. New tool, built 2026-09-23 on an operator direction to stand up a way to query the planning corpus"
ticket: OMN-19236
---

# KB ask (prosthetic)

Take the answer from docs_repo **at `origin/main`, after a refresh**. Never take it from
a working tree, which can be stale or on a feature branch, and never from what you already know.
Everything below is read-only apart from the refresh and a scratch snapshot.

## 1. Resolve the clone, refresh, snapshot

```bash
KB="${DOCS_REPO_PATH:-${registry_root:?set DOCS_REPO_PATH or registry_root}/docs_repo}"
git -C "$KB" remote get-url origin | grep -qE 'OmniNode-ai/knowledge[-_]base[-_]internal' || echo "REFUSE: $KB is not a docs_repo clone"
# Not a git fetch (the lane git-fetch guard, OMN-20495, refuses one from a lane): the canonical-clone
# sync keeps origin/main current; this refresh blocks only until it is at the remote head.
python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh OmniNode-ai/docs_repo --wait >/dev/null || echo "WARNING: refresh failed, reading the last fetched origin/main"
SHA=$(git -C "$KB" rev-parse origin/main); git -C "$KB" log -1 --format='origin/main %h %cI' origin/main
SNAP="${TMPDIR:-/tmp}/kb-ask/$SHA"; mkdir -p "$(dirname "$SNAP")"
if [ ! -d "$SNAP" ]; then   # extract privately, then rename: a parallel run never sees a half-extracted snapshot
  X=$(mktemp -d "$SNAP.XXXXXX") && git -C "$KB" archive origin/main -- ':(exclude)marketing/assets' ':(exclude)ip/figures' | tar -x -C "$X" && { mv -T "$X" "$SNAP" 2>/dev/null || rm -rf "$X"; }
fi
W=$(mktemp -d "${TMPDIR:-/tmp}/kb-ask-run.XXXXXX"); echo "scratch: $W"   # this run's own prompt and result files
# no cd (the shape guard refuses it): every path below is absolute under "$SNAP"
```

- If the remote check prints REFUSE, stop. There is no other default clone.
- If the refresh prints its WARNING, pass it on in the answer.
- The snapshot is keyed by the sha, so it can never be stale. A repeat question on the same sha
  reuses it, and it is read-only for every run. It is extracted into a private directory and renamed
  into place, so two runs started together never read a half-extracted one. Extracting a new one takes
  about 1 s. Never check out, pull or reset the clone itself.
- `W` is this run's scratch directory (`mktemp -d`). Every file the run writes goes there: nothing is
  written to a fixed path such as `${TMPDIR}/kb-ask/prompt.txt`, which two parallel runs would share
  (they did: Known friction). If a later block finds `W` unset because the shell was reset, set
  `W=<the path step 1 printed>`.
- `DOCS_REPO_PATH` may point at a feature worktree. That does no harm, because refs
  are shared and every read is at `origin/main`.

## 2. Choose the search terms

Search is lexical: it finds the words a document actually contains. Write three to six terms as
PCRE fragments that allow the usual variants, for example `plans?`, `releas(e|es|ing)`,
`lab[- ]first`, `C1[1-7]`. Include the words of the question. Also include the words the answering
document would itself use: the formal name, the ticket or rule number, the file or workflow name,
or a synonym. For example, "lab-first rule" alone ranks a CI plan first. Adding `lab is the first`
and `staging` ranks the standing rules guide first.

## 3. Rank the candidate files

Run this against the snapshot (absolute paths, no `cd`), with your terms in place of the examples:

```bash
for t in 'lab[- ]first' 'lab is the first' 'staging' 'promotion'; do
  rg -c -i -P --max-filesize 1M "\\b(?:$t)\\b" -g '*.md' -g '!.github' -g '!scripts' -g '!tests' "$SNAP"
done | sed "s|^$SNAP/||" | awk -F: '{ f=$(1); sub(/^\.\//,"",f); cov[f]++; hits[f]+=$(2) }
  END { for (f in cov) { tier=2
    if (f ~ /^(guides|runbooks|reference)\// || f !~ /\//) tier=1
    if (f ~ /(^beta\/(tracking|handoffs)\/|\/archive\/|evidence-archive|salvage|(TRANSCRIPT|_PROMPTS)\.md$)/) tier=3
    d="-"; if (match(f,/20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]/)) d=substr(f,RSTART,10)
    printf "%d\t%d\t%d\t%s\t%s\n", cov[f], tier, hits[f], d, f } }' \
| sort -t"$(printf '\t')" -k1,1nr -k2,2n -k3,3nr | head -12
```

The columns are: terms matched (coverage), authority tier (1 standing, 2 plan or deep dive,
3 tracking, handoff or archive), total hits, the date in the path, and the path. Rows are sorted by
coverage, then tier, then hits. The awk field references are written `$(1)` and `$(2)` on purpose:
the skill loader replaces a bare dollar-digit with an argument when the skill is called with
arguments.

**Then list what the size cap left out.** `--max-filesize 1M` keeps the 3 MB workflow transcript
out of the ranking. It is not a relevance judgment, and a cap drops files silently. On 2026-09-23 the
old 500K cap dropped `beta/tracking/2026-09-23-worktree-prune.md` (560 KB), the current report on
exactly that subject. Run this with the same terms, joined by `|`:

```bash
T='lab[- ]first|lab is the first|staging|promotion'
find "$SNAP" -name '*.md' -size +1024k | while IFS= read -r f; do
  c=$(rg -c -i -P "\\b(?:$T)\\b" "$f"); [ -n "$c" ] && printf 'excluded-by-size\t%s hits\t%s bytes\t%s\n' "$c" "$(wc -c < "$f" | tr -d ' ')" "${f#"$SNAP"/}"
done
```

A file listed here was not ranked. If it looks like the answer, cut its excerpt with step 4 as
usual, because `rg -n` on one file has no size cap. Otherwise, name it in the answer as
`Excluded by size (not read): <path> (<bytes>)` so the reader knows it exists.

- Take three to five files. Prefer high coverage, then a standing document. Between dated
  documents, prefer the newer one.
- If a lower row is clearly the right document (for example a runbook named for the thing),
  take it.
- `rg` is a Claude Code shell function here, not always a binary on `PATH`, so run the block
  inline, not from a script. Without `rg`, use
  `git -C "$KB" grep -c -i -P "\\b(?:$t)\\b" origin/main -- '*.md' | sed 's|^origin/main:||'` in
  place of the `rg` line. It reads the same ref without the snapshot.

## 4. Cut the excerpts

For each chosen file:

```bash
f="$SNAP/guides/standing-rules-for-collaborators.md"
rg -n '^#{1,6} ' "$f"                                                       # headings, with line numbers
rg -n -i -P '\b(?:lab[- ]first|lab is the first|staging)\b' "$f" | cut -c1-160   # where the hits cluster
sed -n '52,60p' "$f"                                                        # the excerpt
```

- Choose the densest run of hit lines inside one section. Record its heading chain
  (`Title > Section > Subsection`) and its 1-based line range.
- **Caps:** at most 5 excerpts, at most 30 lines each, and at most 6,000 characters in total. Clip a
  single long line (a wide table row) to its relevant part.
- Read each excerpt before you use it. Is it about **this** question? A lexical hit on the same
  words can be about something else. For example, "cut an omnibase_infra release" first matches the
  lab release-train tag runbook, which is not the package release procedure.
- If nothing answers the question, go back to step 2 with different terms. Allow at most three
  retrievals in total.

## 5. Draft the answer on the lab route, then check it

Build the prompt in scratch. Adjust the question and the `path:start-end` list:

```bash
W="${W:?run step 1 first, or set W to the scratch path it printed}"; P="$W/prompt.txt"
{ printf 'Answer the question using only the numbered excerpts below. Cite excerpt numbers in square brackets after each claim. Use no gendered pronoun for anyone (no he, him, his, she, her, hers): write "the operator" or the person'"'"'s role. If the excerpts do not answer it, reply exactly: NOT IN EXCERPTS.\nQuestion: %s\n\n' "<question>"
  n=0; for spec in guides/standing-rules-for-collaborators.md:52-60 guides/collaborator-orchestration-onboarding.md:215-217; do
    n=$((n+1)); f=${spec%%:*}; r=${spec#*:}; printf '[%d] %s lines %s\n' $n "$f" "$r"; sed -n "${r/-/,}p" "$f" | cut -c1-500; echo
  done; } > "$P"; wc -c "$P"
bash "$registry_root/omnibase_infra/scripts/onex" delegate --task-type summarization \
  "$(cat "$P")" > "$W/draft.out" 2> "$W/draft.err"; echo "delegate rc=$?"
python3 - "$W/draft.out" "$W/draft.err" <<'PY'
import json, re, sys
out, err = (open(a, encoding="utf-8", errors="replace").read() for a in sys.argv[1:3])
dec, d = json.JSONDecoder(), None
for m in re.finditer(r"\{", out):          # the result is one JSON object; a banner before it is skipped
    try: obj, _ = dec.raw_decode(out[m.start():])
    except ValueError: continue
    if isinstance(obj, dict) and ("status" in obj or "run_id" in obj): d = obj; break
rid = (d or {}).get("run_id") or next(iter(re.findall(r"runs/([0-9a-f]{8}-[0-9a-f-]{27})/", err + out) + re.findall(r'"run_id":\s*"([^"]+)"', out)), "none")
if d is None:
    print("NO-JSON run_id=%s; stdout %d bytes; last stderr lines:" % (rid, len(out))); print("\n".join(err.strip().splitlines()[-3:]))
else:
    p = (d.get("result", {}).get("terminal_payload") or {}).get("payload") or {}
    print("status=%s run_id=%s model=%s" % (d.get("status"), rid, p.get("model_name"))); print(p.get("response") or "(empty response)")
PY
```

- Use the sanctioned wrapper only. Never use `uv run onex` and never pass `--timeout`.
  `--task-type` must be explicit: a question that says "what is" would otherwise be classed as
  research and climb to cloud rungs. `--criteria` takes declared slugs, never a sentence.
- The route runs on the lab's own models and sends nothing to an external paid API. On 2026-09-23 it
  answered five of five on the local Qwen3.8-27B rung, taking 14 to 58 s of wall time (of which the
  model took 3 to 31 s), at no cost (0 USD). Two of those five drafts needed the check below to become right.
- Stdout (one JSON result) and stderr (the wrapper's banner) go to separate per-run files. The parser
  takes the first JSON object in stdout and, when none parses, still reports the run id from the
  `runs/<id>/` path on the artifacts line, so a failed call is a `NO-JSON run_id=<id>` line and not a
  `jq` parse error with no id.
- Strip any reasoning block before the answer text.
- **No gendered pronouns, for anyone.** The final answer never says he, him, his, himself, she, her,
  hers or herself: write "the operator" or the person's role. Write the answer to `$W/answer.txt` and
  run `grep -n -w -i -E 'he|him|his|himself|she|her|hers|herself' "$W/answer.txt" || echo "pronoun check: none"`;
  rewrite every hit (a quotation of an excerpt inside quotation marks is exempt).
- **Check the draft.** Every claim must be supported by the excerpt its number points at. Delete or
  correct any claim that is not. Add anything the excerpts state that the draft left out, such as a
  dated correction or a rescope. The draft is a first pass, not the answer.
- **Record what you did with the draft** (OMN-20012), once the answer is final: write the answer you
  will output to a file, then
  `python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/delegation_step.py" --omni-home "$registry_root" dispose --lane <your lane> --run <run_id> --disposition <used|edited|discarded> --reason-code <code> --artifact doc:kb-ask:<lane> --final-file <that file>`
  (`--final-file` only when you edited it; a discarded draft takes `--reason-code wrong_answer`,
  `hallucinated` or `incomplete` and no artifact). The edit ratio is measured against the draft, and
  the disposition is published as one bus event keyed by the delegation. Two of five drafts needing the
  check is exactly the number this records.
- **Fallback when the lab route is down,** meaning a non-`success` status, an empty response, a
  refusal, or no result within about 4 minutes: write the answer yourself from the same excerpts,
  under the same rules, and say "lab route unavailable" with the status or run id. One failed READY
  control does not mean the route is down. Try the real prompt once.
- **The Jev plugin (TypeSafe) is not a route here.** It returns typed judgments (choice, yes or no,
  score) from a hosted third-party API and writes no text. Using it to rerank excerpts would send
  private knowledge-base content off the lab.

## 6. Output

```
<answer: one to six sentences or a short list, each claim followed by [n]; give the date of any dated source>

Sources (docs_repo @ <sha10>, origin/main):
- [1] `path` lines a-b, Title > Section
- [2] ...
Route: onex delegate <model>, run <run_id>, checked by this session   (or: session, lab route unavailable: <reason>)
Excluded by size (not read): <path> (<bytes>)   (only when step 3's listing named a file you did not read)
```

- **Not in the KB.** If no excerpt answers the question, reply "Not in the KB." and list the search
  terms of every retrieval you ran. Do not fill the gap from general knowledge or from the session's
  loaded instructions. A session started in registry_root has its CLAUDE.md in context, and that is not
  the knowledge base.
- Only an answer with a citation. When two sources disagree, say so and cite both.
- Use no gendered pronoun for anyone (step 5).
- Keep home-directory paths out of the answer. It may be pasted somewhere shared.

## Known friction (from prior runs)

- **The question's words are not the documents' words.** Terms taken only from the question put a
  CI plan above the standing rules guide, and "where do plans go" leaves one usable term. Add the
  documents' words (step 2). → OMN-19236 evaluation
- **`onex delegate --criteria` takes declared slugs, not free text.** A sentence is refused in about
  7 s, before any model runs, and reads as a model failure. → ledger row 2026-09-23T11:26:17Z FRICTION lane=kb-ask-build existing=OMN-18278
- **A headless run started in registry_root cited a path that came from the loaded CLAUDE.md, not from
  an excerpt.** Check every claim against its excerpt (step 5). → OMN-19236
- **The READY control failed (an empty local response, then a GLM provider error) while real prompts
  succeeded minutes later.** Try the real prompt before calling the route down. → OMN-19236
- **`rg` is a shell function in Claude Code sessions, so it is missing inside `bash script.sh`.**
  Run the blocks inline, or use the `git grep` form (step 3). → OMN-19236
- **`rg --max-filesize 500K` silently dropped a current document.** The 560 KB
  `beta/tracking/2026-09-23-worktree-prune.md` never ranked for a worktree-prune question. The cap is
  now 1M, and step 3 lists every matching file over it as excluded-by-size. Fixed 2026-09-23 by the
  omni-skill-fixes pass, OMN-19230 lineage.
- **The step-3 awk used bare dollar-digit field references, and the route note wrote its cost as a
  dollar sign before a zero.** With arguments the loader replaces each dollar-digit with one of the
  caller's words, so the recipe changed under args. The fields are now `$(1)` and `$(2)`, and the
  cost reads "no cost (0 USD)". Fixed 2026-09-23 by the omni-skill-fixes pass,
  OMN-19230 lineage.
- **The `--criteria` pointer was a ledger line number** that the 2026-09-23 roll made dead. It now
  names the row by timestamp and lane. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230
  lineage.
- **Two questions in parallel shared one prompt file.** Step 5 wrote `${TMPDIR}/kb-ask/prompt.txt` and
  `prompt.json`, and the 2026-10-01 parallel run of the sibling skill `ledger-ask` returned one
  question's draft to the other (the same pattern). Every run now writes under its own `mktemp -d`, and
  the sha-keyed snapshot is extracted privately and renamed into place. → OMN-17427
- **A failed delegate call read as a `jq` parse error with no run id.** The result is parsed from
  stdout alone, with the run id recovered from the artifacts line when the JSON is absent (step 5). → OMN-17427
- **A draft called the operator "he".** The draft prompt and the check step now forbid gendered
  pronouns for anyone. → OMN-17427
