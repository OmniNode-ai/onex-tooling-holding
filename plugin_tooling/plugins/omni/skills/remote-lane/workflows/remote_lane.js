export const meta = {
  name: 'remote-lane',
  description: 'Run one lane brief as headless claude -p on the lab host with the most headroom (onex-remote-lane), through one thin sonnet agent that starts the runner detached and waits for its receipt. Returns the receipt: host, status, duration, the lane result.',
  whenToUse: 'Launch by scriptPath from /omni:remote-lane, or copy its lane() helper into an orchestrator script so a lane spec with host "lab" runs on the lab. args: {skill_dir, lane, brief_path, parent, ticket, prs?, model?, repo?, ref?, host?, timeout_min?}. ticket is the one the lane\'s PRs carry; prs is a space-separated list of repo#n the lane works.',
  phases: [{ title: 'Run' }],
}

/*
 * OMN-17427. The runner does the placement, the plugin set, the ledger rows and the receipt; this
 * script only gets a Workflow agent (whose Bash calls stop at ten minutes) through a longer lane:
 * start detached, then wait in bounded calls until the receipt is final.
 */
const ARGS = (args && typeof args === 'object' && !Array.isArray(args)) ? args : {}
const need = (k) => {
  const v = ARGS[k]
  if (typeof v !== 'string' || !v.trim()) throw new Error(`remote_lane.js: args.${k} is required`)
  return v.trim()
}
const opt = (k, d) => (typeof ARGS[k] === 'string' && ARGS[k].trim() ? ARGS[k].trim() : d)
const SKILL = need('skill_dir').replace(/\/+$/, '')
const LANE = need('lane')
const BRIEF = need('brief_path')
const PARENT = need('parent')
const TICKET = need('ticket')
const PRS = opt('prs', '').split(/\s+/).filter(Boolean)
const MODEL = opt('model', 'sonnet')
if (!['sonnet', 'opus'].includes(MODEL)) throw new Error('remote_lane.js: args.model is sonnet or opus')
for (const [k, v] of [['skill_dir', SKILL], ['lane', LANE], ['brief_path', BRIEF], ['parent', PARENT], ['ticket', TICKET], ['repo', opt('repo', '')], ['ref', opt('ref', '')], ['host', opt('host', '')], ['timeout_min', opt('timeout_min', '')]]) {
  if (v && !/^[A-Za-z0-9_\/.:@-]+$/.test(v)) throw new Error(`remote_lane.js: args.${k} must be a plain token (it is interpolated into a shell command)`)
}
for (const p of PRS) if (!/^[A-Za-z0-9_.-]+#[0-9]+$/.test(p)) throw new Error(`remote_lane.js: args.prs entry ${JSON.stringify(p)} must be repo#n`)
const flagsFor = (lane, host) => [
  `--brief ${BRIEF}`, `--lane ${lane}`, `--model ${MODEL}`, `--parent ${PARENT}`, `--ticket ${TICKET}`,
  ...PRS.map(p => `--pr ${p}`),
  opt('repo', '') ? `--repo ${opt('repo', '')}` : '',
  opt('ref', '') ? `--ref ${opt('ref', '')}` : '',
  host ? `--host ${host}` : '',
  opt('timeout_min', '') ? `--timeout-min ${opt('timeout_min', '')}` : '',
].filter(Boolean).join(' ')
const CMD = `python3 ${SKILL}/scripts/onex_remote_lane.py`
const RECEIPT = {
  type: 'object',
  properties: {
    exit_code: { type: 'number' }, status: { type: 'string' }, host: { type: 'string' },
    duration_s: { type: 'number' }, result: { type: 'string' }, receipt: { type: 'string' },
  },
  required: ['exit_code', 'status'],
}

// Exit 77 (OMN-17427): the host's Claude account hit a usage limit. The runner has already marked that
// host in the controller's placement directory, so a second run without the pin lands on another host.
const EXIT_HOST_LIMITED = 77
// Exit 79 (OMN-20498): the host's Claude login expired; the runner marked it until an operator clears it, so the
// same unpinned retry lands elsewhere.
const EXIT_HOST_AUTH_EXPIRED = 79
const hostOut = (code) => code === EXIT_HOST_LIMITED || code === EXIT_HOST_AUTH_EXPIRED
const runOnce = (lane, host) => agent(
  `Run exactly this shell command once, with a Bash timeout of 180000 ms (placement waits up to 90 seconds): ${CMD} run ${flagsFor(lane, host)} --detach
It prints a line with receipt=<path>, waits up to 90 seconds for placement, and prints a PLACEMENT line last (OMN-20840).
If it exits 0 or 3 (placed, or still placing), run \`${CMD} wait --receipt <that path>\` (a Bash timeout of 600000 ms), and repeat that wait call until its exit code is not 3.
Return the final receipt JSON's exit_code, status, host, duration_s, result and receipt fields, unchanged. If the first command exits with any other code, the lane never ran: return that exit code as exit_code, the status the PLACEMENT line names (no-host, host-limited, failed ...; "start-failed" when it printed none), the PLACEMENT line as result and the receipt= path as receipt.
Do not do the lane's work yourself, do not edit anything, and do not retry a lane that failed.`,
  { label: `${lane}@lab`, phase: 'Run', model: 'sonnet', effort: 'low', schema: RECEIPT })

phase('Run')
let receipt = await runOnce(LANE, opt('host', ''))
if (hostOut(receipt.exit_code)) {
  log(`remote lane ${LANE}: host ${receipt.host} is out (${receipt.status}, marked); retrying once on another host`)
  const first = receipt
  receipt = await runOnce(`${LANE}-r2`, '')
  receipt = { ...receipt, retried_after: { lane: LANE, host: first.host, status: first.status, receipt: first.receipt } }
}
log(`remote lane ${LANE}: host=${receipt.host} status=${receipt.status} exit=${receipt.exit_code} duration_s=${receipt.duration_s}`)
return receipt
