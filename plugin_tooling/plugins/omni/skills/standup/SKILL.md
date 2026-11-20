---
name: standup
description: Draft one person's daily standup status for a non-technical reader (the cofounder), made of one plain headline sentence, two to five grouped themes of system work (what users can do now, reliability, speed of shipping, cost) each with one outcome sentence and a rough count of changes, the M4 delegation line in plain words, and a final "Still blocked:" naming who must act. No ticket or pull request ids in the body, no internal vocabulary, 170 words at most. Facts come from GitHub through gh and from Linear for that person only, plus Slack asks if the Slack tools are present. A stdlib checker enforces the shape and a failing draft is rewritten, not shown. Never posts to Slack unless the person opts in for that message. Use for "write my standup", "status update", "daily report", or before any post to the standups channel.
prosthetic: true
replaces_when: "A status projection on the bus renders each person's standup from typed facts and the dashboard shows it, on two consecutive days."
restored_from: "Rewrites the per-subsystem standup skill of OMN-17427 (plugin-tooling-pkg#157, 250-word cap, operator-only sources) for the team format posted on 2026-09-29. One tool for everyone, so every status reads the same."
ticket: OMN-20176
argument-hint: "[<name or gh login>] [--since <ISO instant>] [--until <ISO instant>] [--reply-to <standups message ts>] [--post]"
---

# Standup (prosthetic)

The reader is the cofounder, who is not an engineer and reads this between other work. He asked
(standups channel, 2026-10-21) for reports that say what was done, what the major issue is and what it
means for moving the product forward, not machine-written lists. The operator ruled the format on
2026-10-22 (OMN-17427): readable for a non-technical person, only the system information that person
needs, in the style of the dashboard owner's status posts, with system work described in groups
because the volume of changes is now large.

What makes the dashboard owner's posts readable, and what this format copies:

- One line per area of work, each opening with the outcome ("Overview, Runs, and Usage now support
  tier mix"), never with the mechanism.
- Four to six lines in all, so the whole post fits one screen.
- A closing "Still blocked" line that says what waits and on whom.
- A count of what finished ("5 tickets reached Done"), so size is visible.

What it drops from those posts: ticket and pull request ids in the lines, internal tool names, and
"no gates bypassed" lines. A reader who cannot act on an id should not meet one.

```
[Headline: one plain sentence, what people can do now or the biggest thing that changed.]

*What users can do now:* [One outcome sentence.] (about 7 changes)
*Reliability:* [One outcome sentence.] (about 14 changes)
*Speed of shipping:* [One outcome sentence.] (about 12 changes)

M4 delegation: [Where delegation stands, in plain words.]

Still blocked: [What people cannot do yet, who must act, and on what.]
```

Themes are the groups of work, not the changes. Use the ones that moved, two to five of them:
*What users can do now* (features and fixes a user would notice), *Reliability* (breaks less,
recovers alone, alarms sooner), *Speed of shipping* (how fast and how safely work reaches users),
*Cost* (what runs cheaper, what is metered), *Safety* (keys, access, security). Record-keeping and
housekeeping changes join no theme unless they change speed. Each theme is one line, one outcome
sentence of 40 words at most, and a rough count of the changes in it ("about 14 changes").

## Who and window

1. **Who.** No argument: the invoking person. Their GitHub login is `gh api user --jq .login` and
   their Linear user is `get_user` with `me`. A name or login as the argument: resolve the Linear user
   from the name, and take the GitHub login as given or find it with `gh search users`. If the login
   stays ambiguous, ask once; never guess.
2. **Window.** Default: from that person's last top-level post in the standups channel (`<channel-id>`)
   to now. Read the channel, take the newest message by that person that is not a thread reply, and
   use its timestamp. If the Slack tools are absent or no such post exists, use the previous 24 hours.
   `--since` and `--until` (ISO instants) override both. State the resolved window in the output
   header as UTC instants so the reader can check it.

## Gather facts, that person only

Every source below is one every teammate has. None of them is a local ledger, a lab host or a
hardcoded path.

- **GitHub (required).** Run the fact sheet; it calls `gh` only and records a failing call instead of
  stopping, so read its `errors` line before trusting a count:

  ```bash
  python3 "${CLAUDE_SKILL_DIR}/scripts/standup_facts.py" --who <login> --since <ISO> --until <ISO>
  ```

  It lists the person's pull requests merged and opened in the window, their open pull requests that
  are red or waiting on someone (with the failing checks and who is asked), and review requests
  waiting on them. Two more sections say what the work changed. `milestone` is the published beta
  board read through `gh` at the window start and now: the cleared count at both instants, and each
  probe whose state changed, with its criterion id, its `description` (the board's own one-line
  condition for that criterion, the wording for what users gained; empty, with an `errors` entry,
  when the board data could not be read), the criterion's carrier tickets and its milestone. The board names carrier tickets, not carrier pull requests, and its log does not say
  which criterion cleared, so a count that moved with no probe change is stated as the count only.
  A window older than the run history is a note, never a guess. `outcomes` groups the person's
  merged and opened pull requests by the `OMN-n` ticket their titles cite, with the milestone and
  criteria when the board names that ticket; its `epic` stays empty here, so take the epic from the
  ticket's parent in the Linear step. `m4_delegation` is where M4 delegation stands (criteria C11-C17
  and C28, with the delegation halves of C29 and C30; C8-C10 are M4.5 cloud and stay out): per
  criterion its probe, proof `state` (`green`, `red`, or `no-probe` when the board has no probe for it),
  `streak`, `last_ok` and `cleared` (true only when the probe reads green), then `proofs_green` of
  `proofs_total`, the M4 `carriers` (Linear tickets) and the whole-board carriers closed of total. The
  board log carries no per-criterion carrier state, so the M4 carrier count is the closed ones among
  `carriers`, read from Linear in the Linear step; when Linear is absent, quote the whole-board count
  and call it that. Criteria the board data does not carry are a note, never a row. Add `--owner <org>` to scope the search to one
  organization, and `--json` to save the sheet for the checker. PR facts and board publication
  metadata come from the PR watcher state; stale, missing or unread fields show as errors, and the
  facts script makes no GitHub read for them. A check reported red can
  still be one of several running, so read the PR before calling it blocked.
- **Linear (required).** With the Linear tools: tickets assigned to the person that reached a
  completed state in the window (`completedAt`), tickets they moved to In Progress or In Review, and
  in-progress tickets that are blocked on someone (a blocking relation, or a comment in the window
  asking a named person). Read the ticket to learn what the work means, not just its title.
- **Slack (optional).** With the Slack tools: messages from people in the window that mention the
  person or reply in their threads and ask them for something (search by the person's Slack user id,
  newest first). Skip bot and notification posts; they are noise, not asks. Without the tools, skip it
  and say so in the sources line.
- **Optional extras.** Anything else the person has locally (a handoff note, a ledger, a worktree) may
  inform the wording. The skill must run, and stay correct, without any of it. An absent extra is
  never an error.

If a required source failed, write the draft from the one that worked and name the gap in the
sources line. Never fill a gap from memory or by guessing.

## Choose what to say

The facts are a pile of activity. The status is a headline, a few groups and one ask.

1. **Headline: what a user can do now.** The first sentence is the capability someone has today that
   they lacked at the start of the window, with the user as the subject: "a Claude Code user can
   delegate from a fresh profile with no approval prompts". Map it from the criteria that went green
   (each `milestone` transition carries its `description`; reword it as what a user can now do, and
   when it is empty say only what the facts show) and from flows proven end to end in a run, not
   inferred from a merge. Not counts, not activity. Rank the available facts and lead with the
   highest rank:
   1. a milestone criterion state change (the `milestone` section: the cleared count moved, or a
      probe that gates a criterion changed state), worded as the capability the criterion's
      `description` names;
   2. a system observed working again (a runtime, gate or pipeline that failed and now passes, seen
      in a run or a probe, not inferred from a merge), worded as what a user can use again;
   3. a decision made (a question answered, a ruling, a choice that unblocks others);
   4. a merge.

   A draft whose first claim is not the highest-ranked available fact fails, and is rewritten.
   When nothing a user can do changed, say so in plain words and name the group that took the
   effort ("Nothing new for users overnight; the work went into keeping delegation dependable").
   A merge is not a deploy: write unproven as unproven.
2. **Group the system work.** Sort the person's merged changes (the `merged` and `outcomes`
   sections) into the themes by what each does for people, each change in exactly one. The count
   is the size of the group, rounded with "about" once it passes thirty. Say one outcome per
   theme in words the cofounder would use: what stopped breaking, what got faster, what costs less.
   Leave a theme out when nothing moved in it; never invent one to fill the shape.
3. **Say it in plain words.** Rewrite internal terms by what they mean to a reader:

   | Instead of | Say |
   | --- | --- |
   | lane, agent session | automated worker |
   | landing controller, merge queue | the automatic system that approves and ships changes |
   | CI, checks, gate | automatic checks |
   | pull request, merge | change, ship |
   | ledger | activity record |
   | hook, guard | safeguard |
   | broker, message bus | the message service |
   | ticket, criterion id (C28) | what it covers, in a few words |

   The checker refuses the left-hand words, code marks, file names and snake_case names.
4. **M4 delegation (always).** One sentence in every draft, whatever else moved, by the
   2026-10-09T00:28:38Z ruling (OMN-17427: people should know where delegation is). Build it from
   `m4_delegation`, worded for a non-technical reader: `M4 delegation: 8 of 9 checks pass; the Claude
   Code plugin check has failed since Oct 16, and 12 of 20 build tasks are done.` Name each red check
   by what it covers, never by its id, with the date its probe last read green (`last_ok`); when the
   section is `unavailable`, say `M4 delegation: unread tonight (<the reason in plain words>)`, never
   a guess. It is not the headline unless it is the highest-ranked fact above.
5. **Still blocked.** The last paragraph, always present. Name the feature people cannot use yet,
   then the person who must act and the one decision or action needed, or `Still blocked: nothing.`
   This is the only place a ticket or pull request reference may appear, at most 2, and only when the
   named person must open it; put the link on the words. Do not invent an owner, a blocker or an ask.
6. **If nothing changed,** say that in the first sentence and say what was learned or ruled out. An
   honest quiet day beats a padded one.

Hard limits: 170 words in all, 3 links at most, 2 ticket or pull request references at most and only
in the last paragraph. Write to the limit; there is no appendix.

## Check before showing

Write the draft to a scratch file (`mktemp`), never into a repository, then run the checker:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/standup_check.py" "<draft file>" --facts "<fact sheet json>"
```

`--facts` takes the sheet saved from `standup_facts.py --json`. It is optional. The checker cannot
judge rank. With it, a milestone transition in the facts that the draft names neither by criterion
id, by probe name, nor with at least half of the longer words of the board's own `description`
prints `STANDUP-CHECK WARN milestone transition absent from draft: <id>`. A warning does not change
the exit code, but read it as the draft missing the first thing the facts show: add the transition
or know why it does not belong. A draft with no sentence on where M4 delegation stands (the phrase
"M4 delegation", any case) also warns: `STANDUP-CHECK WARN no sentence on where M4 delegation
stands`.

It fails loud (exit 1) and names every finding:

- `words`: more than 170 words (a link counts its label, never its URL).
- `first-sentence` and `headline`: the message opens with a preamble ("Today I", "My status") or with
  a themed line instead of one plain claim.
- `themes`, `theme-count`, `theme-long`: fewer than 2 or more than 5 themed lines (a bold label, a
  colon, then the sentence); a theme with no rough count such as "about 12 changes"; a theme longer
  than 40 words or two sentences.
- `jargon`: an internal word (lane, controller, ledger, CI, hook, pull request, merge and the rest
  of the list in the script), a criterion id, a code mark, a file name, a snake_case name or a
  command flag anywhere in the draft.
- `still-blocked`: the final paragraph does not start with `Still blocked:`.
- `ref-list`, `refs-in-body`, `refs`, `links`: a list of ticket or pull request references; any
  reference above the final paragraph; more than 2 references; more than 3 links.

**A failing draft is rewritten and re-checked. It is never shown.** After 3 rewrites that still fail,
show the last draft with the findings, marked FAILED, and say what stops it from passing.

## Output

Print, in this order:

1. The window and sources line: `window <since> .. <until> UTC | sources: GitHub, Linear, Slack |
   missing: <none or the sources that failed>`.
2. The draft, verbatim, in Slack mrkdwn.
3. The checker's own result line (`STANDUP-CHECK OK words=N themes=T links=L refs=R`), copied from its output.

Nothing else is written or sent.

## Posting (opt-in, per message)

**This skill never posts to Slack by default.** A post happens only when the person asks for it in
this turn (`--post`, or "post it"), and is confirmed for that message: show the exact text and the
destination, and wait for a yes. A yes covers that one message only.

- Your own status goes out as a **top-level message** in the standups channel (`<channel-id>`).
- A **response to someone else's status** goes in that post's thread, never as a new top-level
  message. Use `--reply-to <ts>` with the parent's timestamp as the thread. A reply is conversation,
  so the format checker does not apply to it, but keep it short and address the person by name.
- After a post, read the message back from the channel and report its timestamp. If the read-back
  fails, say so and do not claim delivery.

## Existing generators (not replaced here)

Two other sources produce status text: the operator's scheduled Codex automation that writes the
twice-daily "My status for today" and "System status" posts from a full evidence pass (merged-PR
inventory, exact closed-ticket counts, system readiness), and the `onex:system_status` skill, which
reports platform health. Both answer a different question (system evidence for the operator), use
operator-only sources, and stay as they are. The team format belongs to this skill; a scheduled
post that wants it should run `standup_check.py` on its text before sending.

## Known friction

- Generic assistants posted merge counts and full pull request reference lists to the standups channel
  on 2026-09-29. A count of merges is throughput, not proof that anything changed. Lead with the
  change.
- The draft must be checked as a whole. The checker counts every word of the message, a heading
  included, so write to the limit and put nothing in an appendix.
- 2026-10-02 (OMN-20358): a draft built from the person's own merged pull requests led with a minor
  ratchet fix on a night the milestone board went from 6 to 7 criteria cleared, the lab dev runtime
  recovered and merges doubled. The facts held only the person's merges, so the biggest change was
  invisible. Read the `milestone` section first and lead with the highest-ranked fact; the
  checker's `--facts` warning names a milestone transition the draft leaves out.
- 2026-10-02 (OMN-20358): the operator, verbatim: "how about
  sharing what works now that didn't yesterday. nobody cares about the work-ledger. this is about
  having an actual useful product. what features can people use today with delegation. you see how
  that is more useful than pytest issue?" The first claim is the capability a user gained, never the
  internal cause.
- 2026-10-22 (OMN-17427): the cofounder, in the standups channel the evening before: he asked to go
  through the operator's post "to see what this actually means and what it means in terms of what
  actually is done to move the product forward", and said a standard for these reports had been set
  weeks earlier "so it's no longer the ai gibberish". The post named the landing controller, a
  driver mismatch, cloud-credit sessions and criterion ids; none of that tells him what moved. The
  operator ruled (RULING 2026-10-22T06:56:05Z) that the report be readable for him, carry only
  system information a non-technical person needs, follow the dashboard owner's style, and describe
  system work in groups. The checker now refuses the internal vocabulary and requires 2 to 5 grouped
  themes with a rough count each.
