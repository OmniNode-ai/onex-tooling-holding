---
name: harness-delegate
description: "Delegate one task through a CLI harness that is logged in, and only that way: Claude Code on the GLM Coding Plan (z.ai's Anthropic endpoint), claude -p on the Claude subscription, codex signed in with ChatGPT, or the gemini CLI on Vertex AI with Google Cloud SSO. Refuses a harness that is not logged in, or is logged in with an API key, with a typed error and never falls back to a key. Runs in a clean temporary directory, writes the answer and a receipt (harness, model, effort, input size, duration, exit, check result), runs the declared final check, and puts every run on the bus as a delegation event with backend harness:<name>:<model>. Internal operator tooling, not a product delegation tier. Use when a lane or the operator wants a subscription model to draft, summarize, review or answer something, and whenever GLM is wanted (GLM is used only through Claude Code)."
prosthetic: true
replaces_when: "the operator rules the subscriptions retired from delegation, or z.ai grants the separate written agreement its Coding Plan terms name and the lab routes GLM through a general-API key, on two consecutive weeks of lane reports with no harness-delegate run."
restored_from: "none. New skill, from the operator direction of 2026-09-30 about 18:10Z that GLM is used only from Claude Code and that delegation goes only through logged-in harnesses."
ticket: OMN-20173
argument-hint: "run --prompt-file <file> --task-class <class> (--check '<command>' | --rubric <file>) [--harness auto|claude|claude-glm|codex|gemini-vertex] [--model <m>] [--effort low|medium|high] [--host <lab host>] [--writable-repo <worktree>] [--lane <lane>] [--ticket OMN-n]"
---

# Harness delegate (prosthetic)

## Boundary: internal operator tooling, not a product delegation tier

This skill is **not a product delegation tier**. INV-064 (docs_repo
`reference/invariants.yaml`, ruled 2026-06-18) says no delegation tier may be implemented by shelling
out to an external CLI binary, and INV-068 (ruled 2026-08-31) keeps house subscriptions and keys
internal-only and never reachable from a customer tenant. So nothing in omnimarket routing, no
contract overlay and no customer path may call this script. It serves the operator's own work and the
lanes the operator runs, on the operator's own logins.

## Why it exists

The z.ai terms report (docs_repo `reference/zai-glm-coding-plan-terms.md`, OMN-20154)
found that the GLM Coding Plan's quota "is only used within officially supported tools" and may not be
used for "directly invoking model APIs from your own applications ... or other systems". The lab's
delegation node called the Coding Plan endpoint over HTTP, which is that. The operator then ruled that
GLM is used only from Claude Code, and that delegation to any subscription goes through the vendor's own
logged-in tool. This skill is that one path.

## Run it

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/harness_delegate.py" run --prompt-file <task.md> \
  --task-class document --check 'grep -q "## Summary" "$HARNESS_ANSWER_FILE"' \
  --lane <lane> --ticket OMN-<n>
```

- `--check <command>` is the final check. It runs after the harness, in the run directory (or the
  writable repo), with `HARNESS_ANSWER_FILE` set. Exit 0 passes. `--rubric <file>` instead records a
  rubric for the caller to grade (the receipt says `passed: null`). One of the two is required.
- `--harness auto` (default) takes the first logged-in harness in the class order: code classes
  (`code_generation`, `refactor`, `test`, `code_review`, `debug`) try codex, claude-glm, claude,
  gemini-vertex; every other class tries claude-glm, gemini-vertex, codex, claude. The Claude
  subscription is last for text because it is the lane budget.
- `--model`, `--effort` pass through (claude `--effort`, codex `model_reasoning_effort`). Defaults:
  claude `sonnet`, claude-glm `glm-5.3` (use `glm-5.3-flash` for cheap text), codex the ChatGPT
  account's own default (no model flag is passed), gemini-vertex `gemini-2.5-flash`.
- `--writable-repo <worktree>` is the only way a harness gets write access. Without it the run is in a
  fresh temporary directory that is removed afterwards, claude runs with the edit and shell tools
  disallowed (a text-only class, one outside the code classes, also loses `WebSearch`, `WebFetch`, `Glob`
  and `Grep`: its prompt carries the material, OMN-20844), and codex runs in its `read-only` sandbox. With it, claude and claude-glm edit with
  `acceptEdits` and may run Bash so they can run their own checks (OMN-20273), on the same terms as a
  Claude lane: Bash is approved only inside Claude Code's OS sandbox (writes confined to the worktree,
  the sandbox's temp dirs, no network beyond a loopback bind, no unsandboxed escape), the lane's canonical-clone guard
  (`~/.claude/hooks/canonical-clone-guard.py`, reading `registry_root`) is a PreToolUse hook, and git
  mutations (commit, push, stash, reset, clean, checkout, switch, rebase, merge, worktree, config) and
  remote verbs (gh, ssh, scp, rsync, kubectl, aws, docker, curl, wget) are denied: the caller reviews and
  commits. A host without the guard or without `registry_root` refuses the writable run (exit 69). Because
  the sandbox has no network and cannot write the shared uv cache, uv runs with `UV_OFFLINE=1` and
  `UV_NO_CACHE=1`: sync the worktree's venv (`uv sync`) before the run.
- `--host <name>` runs the harness on a lab host from the shared lab host table (the landing
  controller's pool and ssh transport). The script ships itself over ssh stdin and the host runs the
  harness under its own login; the check, receipt and event stay here. `--writable-repo` is local only.
- `--call-budget-s <seconds>` is the whole call's wall clock. It defaults to, and cannot exceed, the task
  class's budget: the `class_budgets_s` value of the `node_delegation_code_budget_compute` overlay, read through
  omnimarket's `read_call_budget_s` in the dispatch venv (OMN-24019, OMN-24023), else 180 for a class the overlay does
  not name or a host where the reader cannot run. The receipt's `config.call_budget_source` says which. The overlay holds
  `code_review` 600 (OMN-20444: glm-5.3 answered 17 of 28 code_review runs at 300 s and 27 of 28 at 600 s; at 180 s it
  answered 14 of 28), `test` 480 (OMN-20844: glm-5.3-flash thinks 75-319 s on a test cell, the slowest cell took 344.3 s
  and the longest first-token wait was 121.85 s) and `code_generation` 600 (OMN-23954). `--timeout-s` still lowers the
  budget to the slice plus 30 s.
- `status [--host <name>] [--json]` prints each harness's login state. `setup-glm --env-file <file>
  --var <NAME>` writes Claude Code's z.ai config (below).

The last stdout line names the harness, model, outcome, check and the receipt path. The answer is
`answer.md` beside `receipt.json` under `<out-dir>/<run id>/` (default
`~/.local/state/omni/harness-delegate`).

## Exit codes

| code | meaning | what you do |
| -- | -- | -- |
| 0 | done; the check passed or the rubric was recorded | read `answer.md` |
| 1 | the harness ran and failed (or timed out; its process group was ended) | read `error.detail` in the receipt |
| 3 | the check failed | the answer is kept; judge it, or run again |
| 64 | usage (no check, a writable repo on a remote host) | fix the call |
| 69 | the harness binary is not installed on that host | install it, or pick another |
| 75 | `--host` is not in the lab pool | check the host table |
| 77 | not logged in, or logged in with an API key | the operator logs in (see below); never set a key |
| 78 | the harness is excluded by its vendor or terms | pick another |

## Logins, and what never happens

The child process gets an allowlisted environment (`PATH`, `HOME`, `USER`, locale, `TMPDIR`, and only
what the harness needs), so no provider key in the caller's environment can reach it. The prompt goes
on stdin, never on argv. No token is ever printed or written to the receipt.

| harness | the login it needs | checked by | how to log in |
| -- | -- | -- | -- |
| claude | Claude subscription (OAuth); an API-key login is refused | `claude auth status` | `claude`, then `/login` |
| claude-glm | Claude Code's own config dir (default `~/.claude-zai`, or `HARNESS_GLM_CONFIG_DIR`) with `ANTHROPIC_BASE_URL` exactly `https://api.z.ai/api/anthropic` and a token; any other endpoint, including the Coding Plan's `/api/coding/paas/v4`, is refused, and an answer from a non-GLM model fails the run | the config file, then the model the run reports | `setup-glm --env-file <file holding the key> --var <NAME>` |
| codex | ChatGPT sign-in; runs with `forced_login_method="chatgpt"` and `--ignore-user-config` | `codex login status` | `codex login`, Sign in with ChatGPT |
| gemini-vertex | Google Cloud SSO application default credentials (a user login, never a service-account key) plus `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`; a reauth error at run time is a typed not-logged-in | the ADC file, then the run | `gcloud auth application-default login` |
| gemini-google | excluded | | Google answered on 2026-09-30 that this client "is no longer supported for Gemini Code Assist for individuals" |

`setup-glm` writes z.ai's documented Claude Code `settings.json` env block (base URL, token, glm-5.3
and glm-5.3-flash model mapping, timeout) with mode 0600 and never prints the key. A key in a local
file is not exposure (Operating Rule 22); do not rotate it for this.

A host with no z.ai config dir but its own key in its infra env (`LLM_GLM_API_KEY` in `~/env-dir/env-file`,
or the file `HARNESS_GLM_ENV_FILE` names) runs GLM with the same env block in the run's environment only:
nothing is written, printed or put on argv, and a config dir, when present, always wins (OMN-17427: every lab
fix lane on h908 on 2026-10-01 failed GLM with exit 77 because setup-glm had never run on the lab hosts). A
host with neither is refused with exit 77 naming both places; the key is placed there by the operator,
never copied between hosts by a lane.

## Terms, per harness

Each receipt carries the line for its harness under `terms`. QUOTED means z.ai's or the vendor's own
words at the URL; INFERRED is our reading.

- **claude (subscription).** QUOTED, https://code.claude.com/docs/en/legal-and-compliance: OAuth "is
  designed to support ordinary use of Claude Code and other native Anthropic applications", and
  "Advertised usage limits for Pro and Max plans assume ordinary, individual usage of Claude Code and
  the Agent SDK." The consumer terms bar automated access "except when you are accessing our Services
  via an Anthropic API Key or where we otherwise explicitly permit it"
  (https://www.anthropic.com/legal/consumer-terms). INFERRED: headless `claude -p` is a documented mode
  of Claude Code used by the subscriber for their own work; keep it individual-scale and never route
  another person's work through it.
- **claude-glm (GLM Coding Plan).** QUOTED, https://docs.z.ai/legal-agreement/subscription-terms
  section 4: the quota "is only used within officially supported tools" and may not be used for
  "directly invoking model APIs from your own applications, bots, websites, SaaS products or other
  systems"; Claude Code is on the supported list (https://docs.z.ai/devpack/tool/others). Limits are
  credits per 5 hours and per week by tier (https://docs.z.ai/devpack/overview); more than three usage
  violations may ban the account (https://docs.z.ai/devpack/usage-policy). INFERRED <owner> zone: a
  headless run started by our script; the plan is licensed to the one subscriber, so it serves the
  operator's own work only.
- **codex (ChatGPT plan).** QUOTED, https://learn.chatgpt.com/docs/auth: "Use API key authentication
  for programmatic Codex CLI workflows, such as CI/CD jobs" and "Don't expose Codex execution in
  untrusted or public environments." Limits are per 5-hour window by plan
  (https://learn.chatgpt.com/docs/pricing). INFERRED: the subscriber's own trusted host, at
  individual volume, is not a CI/CD job; move to an API key if this ever runs unattended at volume.
  The operator's RULING 2026-09-30T18:01:56Z lane=codex-first reverses the 2026-09-29 no-Codex
  ruling and makes Codex the first drafting route for code until the remaining ChatGPT plan period
  ends (about 2026-10-30), which is why `auto` tries codex first for code classes. With no
  `--model`, the skill passes no model flag, so the ChatGPT account's own default answers (the receipt
  names it `codex-account-default`); an explicit `--model` is passed as given. The skill never reads or
  edits codex's `config.toml`.
- **gemini-vertex.** QUOTED, https://geminicli.com/docs/resources/tos-privacy/: Vertex AI use is
  governed by the "Google Cloud Platform Terms of Service", and "Directly accessing the services
  powering Gemini CLI using third-party software, tools, or services is a violation of applicable
  terms" (we run the gemini CLI itself). Billed to the Cloud project; quotas are per project.
- **gemini-google.** Excluded, with the vendor's own refusal above.

## The delegation event

Every run that reached the harness is handed to omnimarket's `node_event_emit_effect` (this script
holds no Kafka client) as a delegate-skill terminal on `onex.evt.omnimarket.delegate-skill-completed.v1`
(or `-failed.v1`), validated first against `ModelDelegateSkillTerminalProjection` in the dispatch venv.
`provider` is `harness:<name>`, `model_name` the model the harness reported, and the one attempt's
`backend_id` is `harness:<name>:<model>`, so the run joins the same `delegation_events` measurements.
The projection has no backend column yet (OMN-20162), so the backend is in `attempt_history` until it
does. The delegate-skill topics are not in the emit registry, so the event rides the registered
`task.delegated` event type (its required `session_id`, `correlation_id`, `task_type` and
`delegated_to` are in the payload).

`--bus-lane <lane>` picks a lane from omnimarket `config/ci_bus_lanes.yaml`; the default is `dev`,
the lane delegation-health reads. `HARNESS_DELEGATE_BUS_LANE` overrides the default; `--bus-lane`
overrides that. Use `host` for the host's own bus without lane resolution. The dispatch venv resolves
SASL identity from the `~/.onex` client store via `onex auth lane-login --lane <lane>`; credentials
are never required in the caller's environment (the fleet's SASL environment can still answer).
If the dispatch interpreter is missing, the runner falls back to the lane map and caller environment;
if that also fails, the receipt names the fallback and remedy. Credentials pass only in the emitter's
environment, never in the receipt or emit request. The `~/.onex` client identity authenticates to the dev
broker but holds no write grant on the delegate-skill terminal topics (only the lane's runtime publishes
them), so when the direct publish comes back `published=false` the script sends the same emit request to the
dev lane's own runtime (compose project, service and the ssh-target variable from the delegation-health
overlay; `HARNESS_DELEGATE_RELAY=off` disables it). The same command body runs locally when `docker ps` on
this host shows a container of the overlay's project and service (the lab host of the dev lane), and over
ssh to the host the overlay's variable names otherwise (OMN-20471); with neither a local runtime nor that
variable the relay fails naming the variable. The receipt's `event.relay` says which path delivered. An
event is `emitted` only when a broker took it. `--no-emit` skips the bus and says so. The receipt's
`event` block holds the topic, the bus (lane, bootstrap and `credential_source`), `published` and the event id.

## The tool_use rubric verdict (OMN-20233)

Claude Code runs (`claude`, `claude-glm`) use `--output-format stream-json --verbose`, so every tool
call and result is kept as `transcript.jsonl` beside `receipt.json`. After the run the script scores it
with omnimarket's tool_use rubric (`omnimarket.delegation.rubric.tool_use_score`, through
`plugins/omni/scripts/tool_use_rubric.py`) and writes `rubric_verdict.json` in the same directory. The
receipt's `rubric_verdict` holds the outcome, failed and undetermined criteria and the record path, and
the delegation event carries it as `attempts[0].rubric_verdict`. The scorer gets the prompt, the tree
the model saw (a writable repo is listed before the run; a clean temporary directory is empty), and the
tools Claude Code offered under the run's flags, captured once per Claude Code version against a
loopback server (no login, no quota; cached under `~/.cache/omni/tool-schemas`). The verdict decides
nothing: a scorer failure is recorded as `UNDETERMINED` with a reason and never changes the exit.
Codex and gemini runs keep no tool transcript and record `reason: no_transcript`. The scorer runs on
the first of `ONEX_TOOL_USE_SCORER_PYTHON`, `ONEX_LAB_WORK_PYTHON`, `$ONEX_DISPATCH_VENV/bin/python`
and `$registry_root/.onex-dispatch-venv/bin/python`; `ONEX_TOOL_USE_RUBRIC=off` skips it and says so.

## Known friction (from prior runs)

- **The launching Mac's own bus points at the lane-i lane's broker.** The first four
  proof runs on 2026-09-30 landed there; the default is now `dev`, with SASL identity resolved from
  the `~/.onex` store via `onex auth lane-login --lane dev`, never required environment credentials.
  `--bus-lane host` explicitly restores the host bus. → OMN-20173
- **The gemini CLI's personal Google login is refused by Google** ("no longer supported for Gemini
  Code Assist for individuals"), and the Vertex ADC on the Mac answered `invalid_rapt` (a reauth is
  due) on 2026-09-30. → OMN-20173
