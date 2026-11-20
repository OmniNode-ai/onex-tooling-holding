<!-- synthetic placeholder fixture, no real data -->
# AGENTS.md

This file is for coding agents. It covers what this directory is and the rules that hold here.
It restates no doctrine. This copy is a synthetic stand-in for the published agent-instruction
document and carries only the section the tests assert.

## Proving a change on the lab before the pull request

Carried here from registry_root#602 (OMN-18893, ticket OMN-0001), because an agent working in
this repository does not load the lane-rules block of the parent workspace.

- A code change is exercised on a lab runtime before the pull request is opened, and the
  pull-request body names the host, the lane, the command and what was observed.
- On `lab-host-a`, prove a branch on a pre-PR slot, never on the shared dev runtime:
  1. Check `lab-host-a` capacity against the runbook floor first. If it fails, stop and report
     the numbers.
  2. Place a ledger HOLD on the slot surface `prepr-<n>-a`.
  3. Bring the slot up with
     `scripts/prepr_verify_lane.sh --slot <n> --worktree <wt> --reason <r>`.
  4. Exercise the change on the slot's ports: 28085/28086 for slot 1, 38085/38086 for
     slot 2.
  5. Destroy the slot with `prepr_teardown_slot.sh --slot <n> --reason <r>`, which sits
     beside the entrypoint, and RELEASE the surface citing its CLEAN report.
- Otherwise prove on `lab-host-c` or `lab-host-b`. Hotpatch the `lab-host-a` dev lane
  only when no slot or surface can carry the proof, and restore it afterwards.
- A slot is a premise for nothing: it is never a proof lane for a stability or production
  grant, and a lab pass is not a staging proof.
- A change that no runtime runs (a maintenance tool, a document, a test) says so in
  the pull-request body and names what it was exercised against instead.

## Where doctrine lives

Doctrine lives in the parent workspace. This file points to it and does not copy it.
