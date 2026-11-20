export const meta = {
  name: 'hotpatch-pr',
  description: 'Hot-patch the installed omni plugin cache from a PR branch, open or already merged, then write the PR marker entries: list the files changed against the PR merge base, write hotpatch_markers.json entries to the worktree copy and to the installed root copy the guards read, back up and install the files into the cache, and verify both marker copies. Dry run unless args.execute is true.',
  whenToUse: 'Launch by scriptPath from /omni:hotpatch-pr with args {skill_dir, worktree, pr} once the branch holds the fix and its PR exists. A PR that has already merged is the ordinary case and needs no extra arguments.',
  phases: [{ title: 'Scope' }, { title: 'Markers' }, { title: 'Install' }, { title: 'Verify' }],
}

// Packaged from the hand-run sequence of 2026-09-28 (hot-patch the cache, open the PR, add
// hotpatch_markers.json entries) per the RULING 2026-09-29T00:33:24Z lane=orchestrator-83 and
// OMN-17427. Decisions live in scripts/hotpatch_pr.py and the installed-tree surface of
// node_plugin_tree_install_effect (both tested). Committing, pushing and opening the PR stay with
// the lane: the marker entries need the PR number, so this runs after the PR exists.
//
// Two changes from FRICTION 2026-11-03T01:29:07Z lane=hotpatch-pool-alarm-0125, where this workflow
// could not run at all and the lane called the four subcommands by hand:
//  - --claude-home is passed. It was not, so the script fell back to ~/.claude, which is a
//    `"plugins": {}` stub on a host whose config directory is elsewhere, and the run died there. The
//    value was in hand: skill_dir is <claude_home>/plugins/cache/<marketplace>/omni/<v>/skills/<name>.
//    args.claude_home overrides it; args.base goes to the script's --base, which is rarely needed.
//  - Markers runs BEFORE Install. A marker has to be a token the installed copy lacks, which it only
//    is before the patch lands; and a refusal then leaves the cache unpatched rather than patched and
//    unmarked, which is exactly the invisible drift the guard exists to catch.
const ARGS = (args && typeof args === 'object' && !Array.isArray(args)) ? args : {}
const need = (k) => {
  const v = ARGS[k]
  if (typeof v !== 'string' || !v.trim()) throw new Error(`hotpatch_pr.js: args.${k} is required`)
  return v.trim()
}
const opt = (k) => (typeof ARGS[k] === 'string' && ARGS[k].trim()) ? ARGS[k].trim().replace(/\/+$/, '') : ''
const SKILL = need('skill_dir').replace(/\/+$/, '')
const WT = need('worktree').replace(/\/+$/, '')
const PR = need('pr')
const EXECUTE = ARGS.execute === true
// The config directory holding plugins/installed_plugins.json: args.claude_home when the lane names
// one, else the ancestor of this skill's own installed path, since the skill runs from inside it.
const HOME = opt('claude_home') || SKILL.split('/plugins/cache/')[0]
const BASE = opt('base')
if (![SKILL, WT, HOME, BASE].every((p) => /^[A-Za-z0-9_\/.:-]*$/.test(p))) throw new Error('hotpatch_pr.js: skill_dir, worktree, claude_home and base must be plain paths')
if (!/^[A-Za-z0-9_.-]+#\d+$/.test(PR)) throw new Error('hotpatch_pr.js: args.pr must be <repo>#<n>')
if (HOME === SKILL) throw new Error('hotpatch_pr.js: args.claude_home is required when skill_dir is not inside <claude_home>/plugins/cache/')
const markerFlags = (Array.isArray(ARGS.markers) ? ARGS.markers : []).map((m) => {
  if (typeof m !== 'string' || !/^[A-Za-z0-9_\/.-]+=[A-Za-z0-9_.:-]*$/.test(m)) throw new Error(`hotpatch_pr.js: marker ${JSON.stringify(m)} must be <file>=<plain token>`)
  return `--marker ${m}`
}).join(' ')
const X = EXECUTE ? ' --execute' : ''
const CMD = (sub, extra) => `python3 ${SKILL}/scripts/hotpatch_pr.py ${sub} --worktree ${WT} --claude-home ${HOME}${BASE ? ' --base ' + BASE : ''}${extra ? ' ' + extra : ''}`
const OUT = { type: 'object', properties: { rc: { type: 'number' }, stdout: { type: 'string' }, stderr: { type: 'string' } }, required: ['rc', 'stdout'] }
const run = (label, cmd, ph) => agent(
  `Run exactly this one hotpatch_pr.py shell command and return its exit code, complete stdout and stderr, unchanged. Do not fix, retry or interpret. Command:\n${cmd}`,
  { label, phase: ph, schema: OUT, model: 'sonnet', effort: 'low' })

phase('Scope')
const changed = await run('changed files', CMD('changed'), 'Scope')
if (changed.rc !== 0) return { outcome: 'refused', at: 'scope', stderr: changed.stderr }
const scope = JSON.parse(changed.stdout)
if (!scope.files.length) return { outcome: 'nothing-to-patch', base: scope.base, note: `the branch changes no plugins/omni or src/ file against ${scope.base}` }
log(`${scope.files.length} plugin file(s) changed against ${scope.base} (${scope.base_reason})`)

phase('Markers')
const marked = await run('marker entries, worktree copy and installed copy', CMD('markers', `--pr ${PR}${X}${markerFlags ? ' ' + markerFlags : ''}`), 'Markers')
// Markers refuses when the installed copy already holds every token a file adds: the payload already
// carries that change, or args.markers must name a better token. Nothing was installed either way.
if (marked.rc !== 0) return { outcome: 'refused', at: 'markers', base: scope.base, stderr: marked.stderr, hint: 'pass args.markers as ["<file>=<token>"], or the payload already carries that file' }

phase('Install')
const installed = await run(EXECUTE ? 'install into the cache (with .bak backups)' : 'install (dry run)', CMD('install', X.trim()), 'Install')
if (installed.rc !== 0) return { outcome: 'refused', at: 'install', base: scope.base, stderr: installed.stderr }

phase('Verify')
const verified = await run('guard on the installed copy, both marker copies', CMD('verify'), 'Verify')
return {
  outcome: EXECUTE ? (verified.rc === 0 ? 'patched' : 'guard-red') : 'dry-run',
  base: scope.base, base_reason: scope.base_reason, files: scope.files,
  install: installed.stdout, markers: marked.stdout, guard: verified.stdout,
  next: 'commit the worktree marker entries (the installed copy already has them), push, then /omni:pr-handoff. No version bump: the post-merge bump PR carries it, OMN-20497. Name the base and why in the PR body.',
}
