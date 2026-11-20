---
name: ledger-ask
description: Answer a question from the rolling work ledger with every claim cited to a ledger row, taken from the ledger and never from general knowledge. The markdown ledger is the authoritative copy; the database work ledger (the work_ledger_rows projection on the lab runtime) is measured against it for the question's window with the projection's own parity check, which gives the database's freshness and the row kinds it holds completely, and rows of those kinds are cited by their database id as well. Search with term coverage, then row kind, then recency, follow a lane's CLAIM to its TERMINAL, draft the answer on the lab delegation route, and check every citation against its row. The answer names which source answered and its freshness. If no row answers, the reply is "Not in the ledger." with the search terms used. A question about whether something merged, landed or deployed is answered with the ledger's silence on GitHub state and the page where the reader confirms it. A WHY question (why did X go wrong, what keeps failing, what blocked Y) runs WHY mode, which groups the window's friction, refused-gate, blocked or failed TERMINAL, CORRECTION and rerun rows by cause, counts and costs each group, and ranks them by cost times recurrence, citing every group's rows. Parallel runs are safe because every scratch path is unique per run and no answer uses a gendered pronoun. Use when anyone asks what the operator decided or consented to, what happened to a pull request, ticket or lane, who touched or resolved something, what friction was recorded, what a lane's last row says, or why work went wrong.
prosthetic: true
replaces_when: "omnimemory or the typed work ledger in ops_tooling_pkg serves ranked, cited row queries over the bus, so that a question returns rows from a maintained index instead of a hand-run grep, on two consecutive weeks of real questions. Today the markdown ledger is still the authoritative copy, and the database projection of its emitted rows misses rows for several kinds (OMN-19513 sets exact parity over one full UTC day as the bar)."
restored_from: "none. New tool, built 2026-10-01 on an operator direction to query the ledger the way the knowledge base is queried"
ticket: OMN-17427
---

# Ledger ask (prosthetic)

The model is `kb-ask`: the same steps, over a different corpus. The corpus here is the rolling work
ledger: one row per line, each starting with a UTC timestamp and a row kind. Answer from the rows
and from nothing else. Everything below is read-only. The only writes are scratch files.

**Scratch is per run.** Step 1 makes one private directory with `mktemp -d` and every later block
writes only inside it (`$W`). Two questions asked at the same time, from one host or several, never
share a prompt, a draft or a result file. A fixed path such as `${TMPDIR}/ledger-ask/prompt.txt` let one
run read the other run's draft (the 2026-10-01 parallel demo, Known friction).

**Which mode.** A question that asks *why* work went wrong ("why did X go wrong", "what keeps
failing", "what blocked Y", "what kept failing on lab hosts today and why") runs WHY mode: steps 1 and
2b, then step 7 in place of steps 2 to 4, then steps 5 and 6. A question about the open CLAIM set
("which lanes are open / claimed and not closed", "who owns PR X or ticket Y right now", "is lane L
still open", "what CLAIMs have no TERMINAL") runs OPEN-CLAIMS mode: steps 1 and 2b, then step 8 in
place of steps 2 to 4, then steps 5 and 6. Questions outside WHY and OPEN-CLAIMS run steps 1 to 6,
including step 2b.

**Which source.** The markdown ledger is the authoritative copy. On a canonical host
`ONEX_LEDGER_PATH` is the live file. On a lab host that writes through the bus
(`ONEX_LEDGER_WRITE_VIA=bus`) it is a read-only snapshot taken when the lane started.

The database work ledger is `private_repo.work_ledger_rows` in the lab runtime's application
database: one row per markdown row the ledger lock emitted, keyed by `row_id` (sha256 of the trimmed
raw row), with `row_ts`, `row_type`, `row_lane`, `tickets` and `raw_row`. It is fed by the dual write
(OMN-19513, on by default since OMN-20248) and projects a new row within seconds, so it is fresher
than any snapshot. It is not complete: a row whose emit was skipped never reaches it, and it also
holds rows that are not in the file. So each question measures it first (step 2b) with
the projection's own parity check: per row kind, how many of the file's rows in the window the
database lacks, and how many database rows are newer than the copy. A row of a kind the database
holds completely is cited by its database id as well as its line. The row text comes from the
markdown ledger, because nothing reads the database rows' text yet (Known friction). The answer says
how fresh each source was and which kinds the database holds completely.

## 1. Resolve the ledger, state the copy and its newest row

```bash
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the ledger file}"
[ -r "$L" ] && [ -d "$(dirname "$L")/archive" ] || echo "REFUSE: $L has no sibling archive/ directory"
LD=$(dirname "$L"); LF="$L"   # no cd (the shape guard refuses it): absolute paths, archive rolls under "$LD"/archive
W=$(mktemp -d "${TMPDIR:-/tmp}/ledger-ask.XXXXXX"); echo "scratch: $W"   # private to this run
et() { python3 -c 'import sys,datetime as d,zoneinfo as z; print(d.datetime.strptime(sys.argv[1],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=z.ZoneInfo("UTC")).astimezone(z.ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET"))' "${1}"; }
utc() { python3 -c 'import sys,datetime as d,zoneinfo as z; print(d.datetime.strptime(sys.argv[1],"%Y-%m-%d %H:%M").replace(tzinfo=z.ZoneInfo("America/New_York")).astimezone(z.ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"))' "${1}"; }
SNAP=''; [ "${ONEX_LEDGER_WRITE_VIA:-}" = bus ] && SNAP=$(date -u -r archive +%FT%TZ)   # a lab copy: the snapshot's time
NEWEST=$(grep -aE '^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z \| ' "$LF" | cut -d' ' -f1 | awk -v s="$SNAP" 's == "" || $(1) <= s' | tail -1)
if [ "${ONEX_LEDGER_WRITE_VIA:-}" = bus ]; then COPY="read-only snapshot on lab host ${ONEX_LEDGER_HOST_NAME:-unknown}, file time $(date -u -r "$LF" +%FT%TZ)"; else COPY="live file on this host"; fi
echo "ledger: $LF ($COPY); newest row $NEWEST = $(et "$NEWEST"); $(wc -l < "$LF") lines live, $(ls "$LD"/archive/*-split.md | wc -l) archive rolls"
```

- If it prints REFUSE, or `ONEX_LEDGER_PATH` is unset, stop and say so. There is no default copy
  (rule 8).
- On a lab host the copy also holds the lane's own rows, appended after the snapshot, so `NEWEST` is
  the newest row at or before the snapshot's time (the `archive/` directory's time, written once
  when the copy is taken), not the file's last line.
- `W` is this run's scratch directory. If a later block finds `W` unset because the shell was reset,
  set `W=<the path step 1 printed>` first. Never make a second directory for one question.
- The echo line goes into the answer's header: which copy, its newest row, and the line count. A
  question about "now" or "just now" is answered only up to that newest row.
- Times the reader sees are Eastern. The ledger's cells stay UTC. `et` converts one UTC stamp, and
  `utc` converts an Eastern `YYYY-MM-DD HH:MM` to UTC (it handles the daylight shift).

## 2. Choose the search terms

Search is lexical: it finds the words a row contains. Write three to six terms as PCRE fragments
that allow the usual variants. Take the question's words, then add the ledger's own vocabulary:

- **Row kind** the answering row has: `RULING` and `OPERATOR-CONSENT` for what the operator decided
  or allowed, `CLAIM` and `TERMINAL` for what happened to work, `FRICTION` for what went wrong,
  `MSG` or `HOLD` for who told whom to wait, `STATUS` for progress.
- **Lane names** (`lane=<name>`), **repo#n** (`omnibase_core#1839`), **ticket ids** (`OMN-17427`),
  host names (`h907`, `.202` as `192\.168\.86\.202` or `h908`).
- **Ruling and consent words** the operator used: `ruled`, `RULED`, `APPROVED SCOPE`, `verbatim`,
  `in-session`.
- **A time window** when the question names one ("today", "yesterday", "at 6pm"). Convert it with
  `utc`: for "today" use the Eastern midnight to now, for example
  `LO=$(utc '2026-10-01 00:00')` and an empty `HI`. A window is a filter on the row's first cell, so
  it never widens the search, it only drops rows outside it.

A bare id is matched as a fixed string (`grep -F`): `omnibase_core#1839` must not read `#` as anything.
Use a PCRE term for words and a fixed string for ids. An id has more than one spelling: a pull
request in `onex_change_control` is written `OCC#12220` as often as `onex_change_control#12220`, and
a lane name often embeds it (`fix-occ-12220`). Search each spelling, and keep the repo prefix on a
number, because the bare digits also match timestamps and counts in unrelated rows.
Friction is recorded on `FRICTION` rows and also in the `friction=` cell of a `TERMINAL`
(`friction=none` means none), so a question about friction searches both.

## 2b. Measure the database ledger for the window

The database is read by the projection's own parity check (omnimarket
`node_projection_work_ledger.parity`, OMN-19513), the one existing tool that reads
`work_ledger_rows`. It reads the markdown ledger and the database for the window, and reports the
file's rows the database lacks and the database rows the file lacks. Connection facts come from the
`delegation_health` overlay (found through `DELEGATION_HEALTH_OVERLAY_PATH` or
`ONEX_SKILL_OVERLAY_ROOTS`): the variable holding the runtime host, the database and its user. The
port is the compose file's published postgres port (`WL_PG_PORT`, default 5436), and the password
comes from the lab env file (`WL_ENV_FILE`, default `~/env-dir/env-file`; a lab host names its own
lane file). The DSN lives in one subshell's environment. Never echo it.

```bash
O="${DELEGATION_HEALTH_OVERLAY_PATH:-$(for r in ${ONEX_SKILL_OVERLAY_ROOTS//:/ }; do [ -r "$r/delegation_health/overlay.yaml" ] && echo "$r/delegation_health/overlay.yaml" && break; done)}"
eval "$(sed -nE 's/^(ssh_host_env|database|db_user): *"?([^"]*)"?$/OV_\1=\2/p' "$O")"; RH="${!OV_ssh_host_env:-}"
CLO="${LO:-$(date -u -d "$NEWEST - 24 hours" +%FT%TZ)}"; W="${W:?run step 1 first, or set W to the scratch path it printed}"
PY="$registry_root/.onex-dispatch-venv/bin/python"; [ -x "$PY" ] || PY="uv run --project $registry_root/omnimarket python"
( set -a; . "${WL_ENV_FILE:-$HOME/env-dir/env-file}" >/dev/null 2>&1; set +a
  export WL_DSN="postgresql://$OV_db_user:$POSTGRES_PASSWORD@${RH#*@}:${WL_PG_PORT:-5436}/$OV_database"; unset POSTGRES_PASSWORD
  $PY -m omnimarket.nodes.node_projection_work_ledger.parity --ledger "$L" \
    --archive-dir "$(dirname "$L")/archive" --since "$CLO" ${HI:+--until "$HI"} --dsn-env WL_DSN > "$W/parity.json" )
RC=$?; echo "parity rc=$RC (0 exact, 1 gaps, 2 error)"
[ "$RC" -le 1 ] && python3 - "$W/parity.json" "$L" "$CLO" "${HI:-$NEWEST}" "$NEWEST" > "$W/cov.txt" <<'PY'
import json, re, sys, collections, glob, os
p, L, lo, hi, newest = sys.argv[1:]; d = json.load(open(p)); f = collections.Counter(); m = collections.Counter()
for path in [L] + glob.glob(os.path.join(os.path.dirname(L), "archive", "*-split.md")):
    for line in open(path, encoding="utf-8", errors="replace"):
        r = re.match(r"^(\S+Z) \| ([A-Z-]+)", line)
        if r and lo <= r.group(1) <= hi: f[r.group(2)] += 1
for x in d["mismatches"]:
    if x["kind"].lower() == "row_missing_in_projection": m[x["detail"].split(" | ")[1].strip()] += 1
only = sorted(x["detail"].split("=", 1)[1][:19] + "Z" for x in d["mismatches"] if x["kind"].lower() == "row_missing_in_file")
newer = [t for t in only if t > newest]
print(f"window {lo}..{d['window_until'][:19]}Z: file {d['file_rows']} rows, database {d['projection_rows']}, missing from database {sum(m.values())}, database-only {len(only) - len(newer)}")
print(f"database rows newer than this copy: {len(newer)}" + (f", newest {newer[-1]}" if newer else ""))
print("per kind (file/missing):", " ".join(f"{k}={f[k]}/{m[k]}" for k in sorted(f, key=lambda k: -f[k])))
print("DB_KINDS='" + "|".join(sorted(k for k in f if m[k] == 0)) + "'")
PY
cat "$W/cov.txt" 2>/dev/null; eval "$(grep '^DB_KINDS=' "$W/cov.txt" 2>/dev/null)"; DB_KINDS="${DB_KINDS:-}"
```

- `DB_KINDS` is the kinds of which the database holds every row the file has in the window. Rows of
  those kinds are cited by their database id as well as their line (step 3). A kind with rows
  missing is answered from the file alone, and its database silence is never evidence.
- The newer-than-copy line is the database's freshness. On a lab host those rows exist only in the
  database, and this skill cannot read their text (Known friction): say how many there are and the
  newest one's time.
- rc 2, or no overlay, env file or route: say `database ledger unreadable: <the error's last line>`
  in the header and answer from the markdown ledger.
- A window older than the database's oldest row shows every kind missing, so the file answers it.
- Copy the lines into the answer's header. Each run measures again: coverage on one day says nothing
  about another.

## 3. Retrieve and rank rows

### Database ids

Search the markdown ledger as below. A row whose kind is in `DB_KINDS` is also cited by its database
id: `row_id` is the sha256 of the trimmed row text, so the id is computed from the row you print,
and step 2b proved that every row of that kind in the window is in the database.

```bash
f=ROLLING_WORK_LEDGER.md; n=23639          # a row of a kind in DB_KINDS
sed -n "${n}p" "$f" | python3 -c 'import sys, hashlib; print("db:" + hashlib.sha256(sys.stdin.read().strip().encode()).hexdigest()[:12])'
```

A row with continuation lines is hashed with them (the parity check joins them the same way).

### Search

Run this in the ledger directory, with your terms. It searches the live ledger and every archive roll,
keeps only real rows (a line whose first cell is a UTC timestamp), and ranks by the number of terms
a row matches, then by row kind (the kinds you name in `KINDS` first), then newest first:

```bash
KINDS='RULING|OPERATOR-CONSENT'    # first for "what did the operator decide"; use 'CLAIM|TERMINAL' for "what happened to X"
LO=''; HI=''                       # UTC window bounds from step 2, or empty
T=('operator' 'siblings?' 'downstream' 'notice')
for t in "${T[@]}"; do grep -aHn -i -E "$t" "$LF" "${LF%"${LF##*/}"}"archive/*-split.md; done \
| awk -v kinds="$KINDS" -v lo="$LO" -v hi="$HI" '{
    p=index($(0),":"); f=substr($(0),1,p-1); r=substr($(0),p+1); q=index(r,":"); n=substr(r,1,q-1); row=substr(r,q+1)
    if (row !~ /^20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9:]+Z \| /) next
    split(row, c, " \\| "); ts=c[1]
    if (lo != "" && ts < lo) next
    if (hi != "" && ts > hi) next
    k=f ":" n; cov[k]++; TS[k]=ts; KD[k]=c[2]
    if (match(row, /\| lane=[^ |]+/)) LN[k]=substr(row, RSTART+7, RLENGTH-7); else LN[k]="-" }
  END { for (k in cov) { tier=(KD[k] ~ ("^(" kinds ")$")) ? 1 : 2
        printf "%d\t%d\t%s\t%s\t%s\t%s\n", cov[k], tier, TS[k], KD[k], LN[k], k } }' \
| sort -t"$(printf '\t')" -k1,1nr -k2,2n -k3,3r | head -15
```

The columns are: terms matched (coverage), kind tier (1 is a kind you named), the row's UTC time, its
kind, its lane, and `file:line`. The line is that file's own line number, so a row in a roll is cited
as `archive/<roll>:<line>` and a live row as `<ledger file>:<line>`. A fixed-string id works the same
way: put `grep -aHn -F -e 'omnibase_core#1839'` in place of the `grep -E` call. The blocks use POSIX
`grep -E` on purpose: `rg` is a shell function in Claude Code sessions and is missing inside
`bash script.sh`, and macOS `grep` has no `-P`. Write terms as POSIX extended regex (no `\S`, `\d` or
lookaround).

- Take the top rows. Prefer high coverage. For "what did the operator decide", a RULING or
  OPERATOR-CONSENT row outranks a MSG that repeats it. A MSG whose text begins `BINDING: operator
  RULING <time>` is the relay of that ruling: cite the ruling row, and the relay only as a second
  source.
- A row that quotes the operator carries the words in quotes with `operator words verbatim:` or
  `(operator, in-session ...)`. Quote those words, do not paraphrase them.

### Follow the chain

- **What happened to a lane or a pull request.** A CLAIM starts a lane, a TERMINAL ends it. Read the
  lane's rows and the rows that close its CLAIM:

  ```bash
  LANE='landing-L1114'
  grep -aHn -E "^[^ ]+ \\| (CLAIM|STATUS|FRICTION|TERMINAL|MSG|HOLD|RELEASE) \\| .*(lane=$LANE( \\||$)|from=$LANE |closes-CLAIM=[^ |]*)" "$LF" "${LF%"${LF##*/}"}"archive/*-split.md | grep -aF "$LANE" | cut -c1-400
  PR='omnibase_core#1839'
  grep -aHn -F -e "pr=$PR" -e "handed-off=$PR" -e "merged=$PR" "$LF" "${LF%"${LF##*/}"}"archive/*-split.md | cut -c1-300
  ```

  A pull request's story is every CLAIM and TERMINAL that names it (`pr=`, `handed-off=`, `merged=`
  or the `repo#n` in prose), oldest to newest. The last TERMINAL's `outcome=` cell says how that
  lane ended, not how the pull request ended: `outcome=done` and `outcome=handed-off` end a lane.
  Say a pull request merged or was resolved only when a row says so (`merged`, `MERGED`, a landing
  `outcome=merged`); otherwise say that no row records it and give the newest row that names it.
  A TERMINAL `closes-CLAIM=` a timestamp, a lane, or a line reference. A line reference was written
  against the ledger as it stood then, and a roll moves lines: confirm it by the CLAIM's timestamp,
  not by the number.
- **A question about a merge, a landing or a deploy** ("did it merge", "has it landed", "is it
  deployed", "is it in main"). The ledger records what lanes wrote, not GitHub state, and a lane writes
  a merge only if it saw one. Answer in this order:
  1. Say `the ledger does not record GitHub state` and give the newest row that names the pull
     request, and any row that says `merged` (cite it as a lane's claim, with its time).
  2. Tell the reader to confirm on GitHub, and give the page: `https://github.com/<owner>/<repo>/pull/<n>`
     (the owner and repository come from the row's `repo#n`). This skill makes no GitHub call: the
     canonical-file-shape ratchet (OMN-20304) counts a GitHub CLI pull-request command in a SKILL.md as
     an imperative line and refuses it, so the confirmation is the reader's.
  3. A deploy is not on a pull request page. Say no row records it and name where it is read (the
     release or deploy surface); do not infer it from a merge.
- **A row's detail pointer.** A row can name a file under `ledger-detail/` in the registry's
  `.claude_scratch/`, or say `detail=...` inline. Read the file with `sed -n` and cite it as
  `ledger-detail/<file>:<line>`. If the file is absent on this host, say so and cite only the row.
- A `MSG` that points at an earlier row (`re=`, `follows=`, `source=`) is followed one hop.

## 4. Cut the excerpts

For each chosen row:

```bash
f=ROLLING_WORK_LEDGER.md; n=23639          # the file and line from step 3
sed -n "${n}p" "$f" | cut -c1-1200         # the row, clipped
sed -n "${n}p" "$f" | grep -a -o -i -E ".{0,200}(siblings?|downstream).{0,300}"   # the part around the hit, for a long row
```

- **Caps:** at most 10 rows, at most 1,200 characters each, and at most 8,000 characters in total. A
  chain of CLAIM and TERMINAL rows counts row by row.
- Record, for each row, its `file:line`, its UTC time, its kind and its lane. The line number is the
  citation, so print it from the same `sed` or `rg` you cut the text from.
- Read each row before you use it. A lexical hit can be about something else: `.202` matches a
  disk-cleanup consent and also an unrelated IP in a log row.
- If nothing answers the question, go back to step 2 with different terms. Allow at most three
  retrievals in total.

## 5. Draft the answer on the lab route, then check it

Build the prompt in scratch (`$W`, from step 1) from the rows you cut, or take `$W/why-prompt.txt`
from step 7. Adjust the question and the `file:line` list:

```bash
W="${W:?run step 1 first, or set W to the scratch path it printed}"; P="$W/prompt.txt"
{ printf 'Answer the question using only the numbered ledger rows below. Cite row numbers in square brackets after each claim. Keep every time as written in the row, in UTC. Use no gendered pronoun for anyone (no he, him, his, she, her, hers): write "the operator" or the person'"'"'s role. If the rows do not answer it, reply exactly: NOT IN ROWS.\nQuestion: %s\n\n' "<question>"
  n=0; for spec in "$LF:<line1>" "$LF:<line2>"; do
    n=$((n+1)); f=${spec%%:*}; r=${spec#*:}; printf '[%d] %s line %s\n' $n "$f" "$r"; sed -n "${r}p" "$f" | cut -c1-1200; echo
  done; } > "$P"; wc -c "$P"
bash "$registry_root/omnibase_infra/scripts/onex" delegate --task-type summarization \
  --criteria response_non_empty --criteria final_artifact_only --criteria-mode replace-task-class \
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
  `--task-type` must be explicit. Do **not** pass `--criteria concise`: it caps the answer at 250
  words and fails a long one. `--criteria-mode replace-task-class` with the two declared slugs above
  grades only that the response is non-empty and is the final artifact.
- **Stdout and stderr stay in separate files.** The wrapper prints its banner (task class, transport,
  caller, artifacts) on stderr and the one JSON result on stdout. The parser reads the first JSON
  object in stdout whatever precedes it, and when none parses it still reports the run id, taken from
  the `runs/<id>/` path on the artifacts line or from a `"run_id"` field, so a failed call is a
  `NO-JSON run_id=<id>` line and not a `jq` parse error with no id. Never pipe the two streams into one
  file, and never read a result file another run could write (`$W` is this run's own).
- The route runs on the lab's own models and sends nothing to an external paid API. The ledger holds
  verbatim operator words and private work, so no other route is a fallback for it.
- Strip any reasoning block before the answer text.
- **Check the draft.** For each claim, open the row its number points at and confirm that the row says
  it: the time, the lane, the PR number, the outcome, the quoted words. Delete or correct any claim
  the row does not support. Convert each UTC time to Eastern with `et` (the draft keeps UTC so it can be
  checked against the cell). Add what the rows state that the draft left out, such as a later
  TERMINAL that changed the outcome. The draft is a first pass, not the answer.
- **No gendered pronouns, for anyone.** The final answer never says he, him, his, himself, she, her,
  hers or herself. Write `the operator` or the person's role (`the orchestrator`, `the reviewer`, `the
  lane`). Write the answer to `$W/answer.txt` and run:

  ```bash
  grep -n -w -i -E 'he|him|his|himself|she|her|hers|herself' "$W/answer.txt" || echo "pronoun check: none"
  ```

  Rewrite every hit. The only text exempt is a quotation of a row inside quotation marks, which stays
  as written; keep the pronoun out of the sentence around it.
- **Say what you did with the draft** on the Route line: `used`, or `edited` with what changed (a
  claim cut, a claim added, a time converted). `delegation_step.py dispose` is not used here: it
  refuses the receipt a raw `onex delegate` call writes (`dispose requires an ok/incumbent
  real-engine receipt`), and a refused record is worse than a stated one.
- **Fallback when the lab route is down,** meaning a non-`success` status, a `NO-JSON` line, an empty
  response, a refusal, or no result within about 4 minutes: write the answer yourself from the same
  rows, under the same rules, and say `lab route unavailable: <status or run id>`. Try the real prompt
  once before calling the route down.

## 6. Output

```
Ledger: <file> (<copy>), newest row <UTC> = <ET>, <n> lines
Database: work_ledger_rows; window <lo>..<hi>: file <n> rows, database <n>, missing from database <m>; complete kinds: <DB_KINDS, or none>; <k> rows newer than the copy, newest <UTC> = <ET>, text not readable here (or: database ledger unreadable: <reason>)
Answered by: markdown ledger text; database-complete kinds cited by database id too

<answer: one to six sentences or a short list, each claim followed by [n]; Eastern times, with the
UTC cell in parentheses where a reader may want to find the row>

Sources:
- [1] `ROLLING_WORK_LEDGER.md:<line>` <UTC time> <KIND> lane=<lane>
- [2] `archive/<roll>:<line>` ...
- [3] `ROLLING_WORK_LEDGER.md:<line>` = `db:<id12>` <UTC time> <KIND> lane=<lane>   (a kind in DB_KINDS)
Confirm on GitHub: https://github.com/<owner>/<repo>/pull/<n>   (only for a merge question; the ledger records no GitHub state)
Route: onex delegate <model>, run <run_id>, draft <used|edited: what changed>, checked by this session   (or: session, lab route unavailable: <reason>)
```

- **Not in the ledger.** If no row answers the question (a nearby row that does not say it is not an
  answer), skip the draft and reply "Not in the ledger." and list the
  search terms of every retrieval you ran, and the time window if one was set. Do not fill the gap from
  general knowledge, from the session's loaded instructions, or from a pull request's own page. A
  session started in registry_root has its CLAUDE.md in context, and that is not the ledger.
- Only an answer with a citation. When two rows disagree, say so and cite both, newest first.
- Give a database id only for a kind in `DB_KINDS`. For any other kind the database misses rows, so
  its silence is not evidence.
- State a snapshot's limit: if the copy is a lab-host snapshot and the question is about the last few
  minutes, say that rows newer than its newest row are not read, and give step 2b's count of database
  rows newer than the copy.
- Use no gendered pronoun for anyone (step 5). Say `the operator` or the role.
- Keep home-directory paths out of the answer. It may be pasted somewhere shared. Name the ledger
  file, not its directory.

## 7. WHY mode: why did it go wrong, what keeps failing, what blocked it

A WHY question is answered from groups of rows, not from a handful of hits. Run steps 1 and 2b first
(the window is `CLO` to `HI`, default 24 hours back from the newest row; "today" is Eastern midnight
to now through `utc`). Then gather, group, rank, draft (step 5) and check.

**What is reused.** This skill adds no script and no reader of its own. The row grammar is
`friction-record`'s (`ticket=`, `existing=` or `tickets=`, a `cost=` cell that carries a duration, and
`class=`, `surface=`, `guard=`, `reason=` on hook rows). The row reader is the ledger verb
`onex_ledger.py query` that `ledger-catchup` and `friction-record` step 1 read through, with
`ledger-catchup`'s cell rule (a key is read from a cell that starts with it, never from prose, so
`supersedes-id=` is not `id=`; a row is a line whose first cell is a UTC timestamp). Checked on
2026-10-01: `friction-classify` and `morning-friction-sweep` are workflows in
`ops_tooling_pkg/src/ops_tooling_pkg/handlers/` (JavaScript run by the workflow tool), not
skills, and their row parsers are functions inside those files, so a SKILL.md has nothing to call.
What this step takes from them is their vocabulary, not a second parser: `friction-classify` names a
row by `class`, `cost` and `surface`, and the sweep profiles hook refusals by gate and reason and
groups failures by check name across pull requests. The grouping key below is that: `class=`, then
`surface=`, and `guard=` with `reason=` for a refusal. `friction-record` names the sweep as the harvester
of the FRICTION row. Where a workflow's own report for the day exists, cite it as a second source and
do not recount it.

**What counts.** In the window:

- every `FRICTION` row. A hook row (`class=refusal`, with `guard=` and `reason=`) is a **refused
  gate**; any other row is grouped by its `class=` or `surface=`, else its first six words;
- every `TERMINAL` row whose `outcome=` is `blocked`, `external_blocker` or `failed`, and every
  `outcome=handed-off` row whose `result=` is `external_blocker`, `failed`, `blocked` or `red`
  (handed off with a red result), grouped by outcome, repository (from `pr=` or `handed-off=`) and
  host (`host=`, `via=bus:<host>`, or `host <name>` in the row's text);
- every `CORRECTION` row, grouped by the ticket it names;
- repeated reruns: a lane whose name ends `-r<n>`, `-rerun`, `-retry`, `-attempt<n>` or `-redo` and
  whose base name has a CLAIM too, or has more than one such CLAIM.

A question that names hosts ("on lab hosts", "on h908") sets `HOST_RE` (`h[0-9]{3}` for lab hosts,
`h908` for one). Rows with no host are then left out, which includes the hook rows, and the answer says
so. A question that names a repo, a ticket or a skill adds a `grep -F` filter on the gathered rows.

**Gather, group, rank.** The groups are cause keys: the same gate and reason, the same class, the same
outcome on the same repository and host. Each group gets its row count, its distinct lanes, the sum of
its `cost=` cells in lane-minutes (hours are multiplied by 60; rows with no parseable cost are counted
and named, never guessed), the tickets its rows cite with each ticket's open work, and its newest
rows. The rank is **cost times recurrence**: `rows x max(cost minutes, rows)`, so a group with no
cost cells counts each row as one lane-minute and a recorded cost counts for what it says. The ticket's
open state comes from the ledger only: a ticket has open work when a lane's CLAIM naming it has no
later TERMINAL in the window. Linear's own status is not read here, so the answer says `open work on
the ledger` and never `open in Linear`.

```bash
W="${W:?run step 1 first, or set W to the scratch path it printed}"; WHI="${HI:-$NEWEST}"; HOST_RE="${HOST_RE:-}"   # HOST_RE='h[0-9]{3}' for a lab-host question
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" query --ledger "$L" --archives --kind CLAIM,TERMINAL,FRICTION,CORRECTION \
  --since "$CLO" --detail-dir "$W" > "$W/why-query.txt"
D=$(sed -nE 's/.* detail=([^ ]+).*/\1/p' "$W/why-query.txt" | head -1); head -1 "$W/why-query.txt" | cut -c1-200
python3 - "$D" "$CLO" "$WHI" "$W" "$HOST_RE" "${DB_KINDS:-}" <<'PY'
import collections, hashlib, json, os, re, sys
detail, lo, hi, w, host_re, db_kinds = sys.argv[1:7]
db_kinds = set(k for k in db_kinds.split("|") if k)
BAD_OUT = {"blocked", "external_blocker", "failed"}
BAD_RES = {"external_blocker", "failed", "blocked", "red"}
RERUN = re.compile(r"(-r\d+|-rerun\d*|-retry\d*|-attempt\d+|-redo\d*)$")
rows = []
for line in open(detail, encoding="utf-8", errors="replace"):
    m = re.match(r"L\d+ (20\S+Z) \| ([A-Z-]+) \| ?(.*)$", line.rstrip("\n"))
    if not m or not (lo <= m.group(1) <= hi): continue
    cells = [c.strip() for c in re.split(r"\s*\|\s*", m.group(3))]
    i = 0
    while i < len(cells) and re.match(r"^[A-Za-z_-]+=", cells[i]): i += 1
    rows.append(dict(ts=m.group(1), kind=m.group(2), text=m.group(0).strip(), struct=" ".join(cells[:i]), prose=" | ".join(cells[i:]),
                     raw=line.rstrip("\n").split(" ", 1)[1]))
def cell(r, k):
    m = re.search(r"(?:^| )" + re.escape(k) + r"=(\S+)", r["struct"]); return m.group(1) if m else ""
def host(r):
    h = cell(r, "host") or (cell(r, "via").split(":")[-1] if cell(r, "via").startswith("bus:") else "")
    if not h:
        m = re.search(r"\bhost (h\d{3})\b", r["raw"]); h = m.group(1) if m else ""
    return h
def minutes(r):
    m = re.search(r"cost=~?(\d+(?:\.\d+)?)\s*(?:lane-)?(minutes?|mins?|hours?|hrs?)\b", r["struct"] + " " + r["prose"][:200])
    if not m: return None
    return float(m.group(1)) * (60 if m.group(2).startswith("h") else 1)
def tickets(r):
    out = []
    for k in ("ticket", "existing", "tickets"):
        out += [t for t in cell(r, k).split(",") if re.match(r"OMN-\d+$", t)]
    return out
unclosed = {}
claim, done = {}, {}
for r in rows:
    ln = cell(r, "lane")
    if r["kind"] == "CLAIM": claim[ln] = r
    elif r["kind"] == "TERMINAL": done[ln] = r["ts"]
for ln, r in claim.items():
    if ln not in done or done[ln] < r["ts"]:
        for t in tickets(r): unclosed[t] = unclosed.get(t, 0) + 1
G = collections.OrderedDict()
def add(key, r, why):
    g = G.setdefault(key, dict(key=key, why=why, rows=[]))
    g["rows"].append(r)
base = collections.defaultdict(list)
for r in rows:
    if host_re and not re.fullmatch(host_re, host(r) or "-"): continue
    k, ln = r["kind"], cell(r, "lane")
    if k == "FRICTION":
        if cell(r, "class") == "refusal": add("refused-gate: %s (%s)" % (cell(r, "guard") or "?", cell(r, "reason") or "?"), r, "refused gate")
        else:
            c = cell(r, "class") or cell(r, "surface") or " ".join(re.sub(r"^[^A-Za-z]+", "", r["prose"]).lower().split()[:6]) or "unlabelled"
            add("friction: " + c, r, "FRICTION")
    elif k == "CORRECTION": add("correction: " + (tickets(r) or [ln])[0], r, "CORRECTION")
    elif k == "TERMINAL":
        o, res = cell(r, "outcome"), cell(r, "result")
        if o in BAD_OUT or (o == "handed-off" and res in BAD_RES):
            pr = cell(r, "pr") or cell(r, "handed-off"); repo = re.split(r"[#,]", pr)[0] or "-"
            add("terminal %s on %s @%s" % (o if o in BAD_OUT else "handed-off result=" + res, repo, host(r) or "-"), r, "TERMINAL")
    elif k == "CLAIM" and RERUN.search(ln): base[RERUN.sub("", ln)].append(r)
for b, rs in base.items():
    others = sum(1 for r in rows if r["kind"] == "CLAIM" and cell(r, "lane") == b)
    if len(rs) + others >= 2:
        for r in rs: add("rerun: " + b, r, "repeated rerun")
out = []
for g in G.values():
    rs = g["rows"]; cm = [minutes(r) for r in rs]; cost = sum(c for c in cm if c); unk = sum(1 for c in cm if c is None)
    t = collections.Counter(x for r in rs for x in tickets(r))
    g.update(n=len(rs), cost=cost, unk=unk, lanes=len({cell(r, "lane") for r in rs}), tickets=t, score=len(rs) * max(cost, len(rs)))
    out.append(g)
out.sort(key=lambda g: (-g["score"], -g["n"], g["key"]))
def dbid(r): return "db:" + hashlib.sha256(r["raw"].strip().encode()).hexdigest()[:12]
def cite(r): return "%s %s lane=%s%s" % (r["ts"], r["kind"], cell(r, "lane") or "-", (" " + dbid(r)) if r["kind"] in db_kinds else "")
print("window %s..%s: %d rows read, %d groups" % (lo, hi, len(rows), len(out)))
total = 0
with open(os.path.join(w, "why-prompt.txt"), "w") as P:
    for i, g in enumerate(out[:10], 1):
        tk = ", ".join("%s (%d rows, %s)" % (t, n, ("open work on the ledger: %d unclosed CLAIM" % unclosed[t]) if t in unclosed else "no unclosed CLAIM in window") for t, n in g["tickets"].most_common(3)) or "none cited"
        print("G%d score=%g rows=%d lanes=%d cost=%gmin%s | %s | tickets: %s" % (i, g["score"], g["n"], g["lanes"], g["cost"], (" (+%d rows with no cost)" % g["unk"]) if g["unk"] else "", g["key"], tk))
        for r in sorted(g["rows"], key=lambda r: r["ts"], reverse=True)[:3]:
            print("    cite " + cite(r))
        if i <= 6:
            for j, r in enumerate(sorted(g["rows"], key=lambda r: r["ts"], reverse=True)[:3], 1):
                slim = " | ".join(c for c in re.split(r"\s*\|\s*", r["raw"]) if not re.match(r"(actor|model|handed_to|engine_rc|friction=none|dedupe|lane_source|suppressed)", c))
                s = "[G%d.%d] %s\n%s\n\n" % (i, j, cite(r), slim[:600])
                if total + len(s) <= 8000: P.write(s); total += len(s)
json.dump([dict(key=g["key"], n=g["n"], cost=g["cost"], score=g["score"], cites=[cite(r) for r in g["rows"]]) for g in out], open(os.path.join(w, "why.json"), "w"), indent=1)
PY
```

- The first line is the verb's own count of rows by kind. The `window ...: <n> rows read` line after it
  is the same rows after the window and host filters; the two must agree when `HOST_RE` is empty.
- Each group line is `G<i> score rows lanes cost | cause key | tickets`, followed by up to three
  `cite` lines: the row's UTC time, kind and lane, plus `db:<id12>` for a kind in `DB_KINDS`. Cite rows
  by time and lane, never by line number (a roll renumbers). `$W/why.json` holds every group's full
  citation list, and `$W/why-prompt.txt` holds the newest rows of the top six groups as `[G<i>.<j>]`,
  at most 600 characters each (the cells that repeat on every row of a kind, such as `actor=` and
  `model=`, are dropped from the copy) and 8,000 in all.
- Before trusting a short list, run it again with the window widened by a day: a group that appears
  only then names a window too narrow (rule 16). A zero on a kind (no TERMINAL group at all) is
  checked against `grep -c ' | TERMINAL | '` on the same window before it is reported.
- The causes are in the rows' prose, not in the grouping key. Read the cited rows of each group you
  report (`sed -n` on the row, or the detail file) and say what they say went wrong, in their words
  and their numbers. A key only says rows resemble each other.

**Draft.** Step 5 with `$W/why-prompt.txt` as the rows and this task line in place of the question's:
`For each group, state in one sentence what the cited rows say went wrong, citing [G<i>.<j>]. Do not
add a cause the rows do not state.` Then the check: each group's count, cost, tickets and cause
against the group lines and the rows; each cause against the row it cites; the pronoun check.

**Answer shape** (one block per group, at most eight, ranked, each citing its rows):

```
Window <lo>..<hi> (<ET>), <n> rows read, <g> groups, ranked by rows x max(cost minutes, rows); host filter <none|HOST_RE>
1. <cause key>: <n> rows over <k> lanes, <c> lane-minutes recorded (<u> rows with no cost). Cause: <what the rows say> [1.1][1.2]. Tickets: OMN-<n> (<open work on the ledger | no unclosed CLAIM in the window>).
   Rows: <UTC> <KIND> lane=<lane> [db:<id12>], <UTC> <KIND> lane=<lane>, ...
2. ...
```

Then the header and the Route line of step 6. If the gather returns no group, reply `No failure rows in
the window.` with the window and the counts of each kind, not "Not in the ledger." A question the
groups do not answer (`what blocked Y` for a Y no row names) is `Not in the ledger.` with the terms.

## 8. OPEN-CLAIMS mode

Run steps 1 and 2b, then use the ledger verb to find CLAIMs with no closing TERMINAL:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" open-claims --ledger "$L" --detail-dir "$W" > "$W/open-claims.txt"
head -1 "$W/open-claims.txt"
grep -F 'ticket=OMN-17427' "$W/open-claims.txt"   # or lane=<name>, or host=<h>
```

Optional filters are `--lane <name>`, `--since <UTC>` and `--now <UTC>`. The first line is a header
(`open-claims since= claims= open= ledger-newest= now=`), then one line per open CLAIM:
`OPEN-CLAIM lane= claim=<ts> L<line> ticket= newest-row= kind= age= rows= host= run= leases= liveness=unknown`.
Read the header with `head -1` and filter the lines with `grep -F` (a ticket id, a lane, a host)
rather than reading all of them: there are hundreds. The verb accepts `--detail-dir` but today prints the
header and every OPEN-CLAIM line on stdout and names no `detail=` file (checked 2026-10-02 against ops_tooling_pkg#126);
if a later version names one in the header, read it as `ledger-catchup` reads its detail.

Cite each open CLAIM as the `<file>:L<line>` the verb prints. The `L<line>` is in the file named by
the claim cell, e.g. `ROLLING_WORK_LEDGER_..-split.md:L1894` or `ROLLING_WORK_LEDGER.md:L25124`.
For who owns a PR or ticket, filter by the `ticket=` cell and the lane name; a PR no CLAIM names by
ticket needs step 3's follow-the-chain search.

**Limit:** `liveness=unknown` always; the ledger holds no process evidence. Do not call a lane live
or dead from this output. It may report the lane's newest row, its age, `host=` and `run=`. To claim
liveness, the caller cross-checks ListAgents and the remote-lane receipt, and the answer names which
check was made. Draft with step 5 from the selected claims and cited rows, then answer with step 6:
keep the header's Database line and add `Liveness: unknown; ledger holds no process evidence.`

## Known friction (from prior runs)

- **No open-CLAIM-minus-TERMINAL answer.** Friction row 2026-10-02T03:01:17Z (`lane=queue-tick-0258`, `existing=OMN-17427`): ledger-ask had no such answer, so a tick hand-parsed the ledger; step 8 uses the `open-claims` verb. → OMN-17427
- **The question's words are not the rows' words.** "the .202 disk cleanup" is a lane named
  `h908-disk-cleanup` and the address appears only in the row's scope text. Add the lane-name form and the row
  kind (step 2). → kb-ask lineage, OMN-19236
- **`--criteria concise` fails a long answer.** It caps at 250 words. Use `--criteria-mode
  replace-task-class` with `response_non_empty` and `final_artifact_only` (step 5). → OMN-17427
- **A line number in an older row is stale after a roll.** A `closes-CLAIM=` or `source=` line
  reference is checked by the timestamp it names. Cite the line you printed from this copy. → ledger
  row 2026-09-24T20:03:36Z lane=delegation-w1-stop-line-probes
- **`rg` is a shell function in Claude Code sessions, so it is missing inside `bash script.sh`, and
  macOS `grep` has no `-P`.** The blocks use `grep -E` and `grep -F`, which run the same in a session,
  a script and a lane. → OMN-19236, OMN-17427
- **A lab host reads a snapshot.** Rows written after the lane started are absent from it, except the
  lane's own rows, which the bus copies in. Step 2b counts the database rows newer than the copy. →
  OMN-17427
- **The database ledger is not complete, so it is not the primary source yet.** Measured
  2026-10-01 over the 24 hours to 22:14:52Z: the file had 4,091 rows and the database lacked 484 of
  them (FRICTION 247 of 449, STATUS 125 of 234, MSG 54 of 301, CLAIM 29 of 1,511, TERMINAL 26 of
  1,495, OPERATOR-CONSENT 2 of 13, CORRECTION 1 of 4; none of ACK, HOLD, RELEASE or RULING), every
  hour from 03:31Z on, after the 04:08Z backfill had reached zero missing. 244 of the 484 are
  hook-written rows. The database also held 49 rows the file does not (drill and test lanes such as
  OMN-990018). So step 2b measures per question and the file stays authoritative. Closes when the
  dual write reaches exact parity over one full UTC day. → OMN-19513
- **No read path for the database rows' text.** No node, verb or API reads `work_ledger_rows`: `onex
  ledger read` reads the cloud hook ledger, the projection read API (OMN-20152) does not expose it,
  and the ops_tooling_pkg `query` verb reads the markdown file. The skill-shape ratchet
  (OMN-20304) refuses a database client or remote-shell line in a SKILL.md, so SQL retrieval waits for a read
  node. Until then the database measures coverage and freshness, and rows newer than a lab snapshot
  are counted but not read. → OMN-17427
- **`delegation_step.py dispose` refuses a raw `onex delegate` receipt.** kb-ask's step 5 names it
  for the same call, and it exits 2 with `dispose requires an ok/incumbent real-engine receipt` on
  the run's `receipt.json`, and `--lane --run` finds no receipt because none was written under the
  registry's delegation-receipts directory. This skill states the disposition on the Route line
  instead. → OMN-17427
- **A lane's `outcome=done` read as the pull request's outcome.** `fix-occ-12220` ended `done`, and no
  row says `OCC#12220` merged or was resolved. The draft said it was resolved by that lane. Say what
  the row says (step 3, follow the chain). → OMN-17427
- **A merge the brief expected is not a row.** The ledger records lanes, not GitHub state, so a
  pull request's merge appears only if a lane wrote it. Answer "no row records the merge" and give the
  newest row, never the merge from memory. → OMN-17427
- **A MSG relays a RULING word for word.** Ranking by coverage can put the relay first. Cite the RULING
  row as the source and the relay second (step 3). → OMN-17427
- **The skill loader rewrites a dollar-digit when the skill is called with arguments.** The awk
  recipe spells nothing that way and the question is a placeholder, not an argument reference. → OMN-19230 lineage
- **Two questions in parallel read each other's draft.** Both runs wrote `${TMPDIR}/ledger-ask/prompt.txt`
  and `prompt.json`, so the run for question B returned question A's draft from the lab route (the
  22:42Z demo on 2026-10-01). Every path is now under one `mktemp -d` per run (step 1), and the parser
  reads only that run's own files. → OMN-17427
- **A parallel run got a `jq` parse error and no run id from `onex delegate`.** The wrapper writes its
  banner on stderr and one JSON object on stdout, and two runs shared one output file, so a reader saw
  another run's truncated write. The call now writes stdout and stderr to separate per-run files and
  the parser takes the first JSON object and falls back to the `runs/<id>/` path or a `"run_id"` field,
  so the id is kept. A single run did not reproduce the failure: its stdout parsed whole. → OMN-17427
- **The answer called the operator "he".** The ledger names the operator by role, and a draft that guesses
  a pronoun misgenders a person. The rule is in the draft prompt and the check step, with a grep
  over the final answer. → OMN-17427
- **The ledger records lanes, not merges, and a question about a merge was answered from a lane's
  outcome.** Step 3 now says the ledger holds no GitHub state, cites any row that says `merged` as a
  lane's claim, and has the reader confirm on the pull request's page (a GitHub call inside a SKILL.md is refused by the
  OMN-20304 ratchet). → OMN-17427
- **"Why did it go wrong" has no single row.** The cause is spread over friction, refused-gate,
  blocked and failed rows. WHY mode (step 7) groups them by cause, counts and costs each group, and
  ranks by cost times recurrence. → OMN-17427, operator direction 2026-10-01 in session ("we should use
  this to like figure out why things are going wrong")
