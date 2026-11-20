---
name: awaiting-reply
description: List the people who are waiting on the operator for a reply in Slack (direct messages, group messages, @mentions, threads the operator joined) and in Linear (inbox notifications, comments that mention the operator, comments on issues the operator owns or created), over the last 72 hours or a window you pass. An item counts only when the last word is a human's, it asks, requests or hands the turn over, and the operator has not answered since. Bots, alert channels, bare acknowledgements and FYI links are excluded with the reason stated. Each waiting item is then classified AUTO (a status, a fact, an answer that follows from a recorded ruling, routing, an acknowledgement or an agreed follow-up, with its basis named) or ESCALATE (everything else). An AUTO item addressed to one of the two pillar owners is sent by the running session in the same Slack conversation with a "via the operator's agent" footer, and logged on the ledger as a SENT-ON-BEHALF message to the operator; no one else is ever sent to. Output is a plain list of the ESCALATE items grouped by person, oldest wait first, with a link, one line on the ask and the wait, the AUTO sends with their basis, the last 24 hours of sends on the operator's behalf in the morning run, plus suggested replies in the operator's voice written to a local file. An ESCALATE item still waiting after 24 hours is pushed to the operator with its draft, and after 72 hours it is also drafted to the owner of its subject for the operator to approve. It never sends a comment, draft, reaction or reminder, and an ESCALATE reply needs the operator's yes. Use for "who is waiting on me", "anything I need to reply to", or as the scheduled reply check.
prosthetic: true
replaces_when: "A projection of inbound Slack and Linear messages on the bus renders the operator's unanswered asks on the dashboard, with the same exclusions, on two consecutive weeks. Nothing today projects them."
restored_from: "none. New tool, built 2026-10-01 on an operator direction to find who is waiting on a reply, Linear included, and to run on a schedule"
ticket: OMN-20307
mechanism_ticket: OMN-17427
argument-hint: "[<window, e.g. 72h, 24h, 5d>] [--source slack|linear|both] [--person <name>] [--sent]"
---

# Awaiting reply (prosthetic)

A message that is waiting for an answer is invisible once something newer lands above it. People
stop asking twice, and the wait turns into a stall nobody can see. This skill finds the asks that
are still open, says who has waited longest, and answers the ones that rest on facts or an existing
ruling. The answers that need him are drafted for him to edit and send himself.

The rule behind the split is the operator ruling of 2026-10-16T16:30:36Z (lane orchestrator-bb1a,
OMN-17427, kind=process): the orchestrator answers team messages itself when the answer rests on
facts or an existing ruling, and escalates only what is unclear or needs his decision. Section 5a
turns that ruling into a test each item must pass.

It is prompt-only. It uses the Slack and Linear MCP tools of the session it runs in and no script.

## Hard rules

1. **One send, nowhere else.** Never call `slack_send_message_draft`, `slack_schedule_message`,
   `slack_add_reaction`, `mark_notification`, `save_comment`, `save_issue` or any other write tool.
   The single exception is `slack_send_message` for an item section 5a classified AUTO, to a recipient
   on the section 5a allowlist, in the conversation the ask is in. Everything else, including every
   ESCALATE item, needs the operator's explicit yes for that one message, given after he has read the
   draft. Marking a notification read changes what he sees, so that is his act too. The only other
   writes are the ledger row section 5a requires for each send, and the escalation ladder of section 5b,
   which calls `PushNotification` to the operator and writes its own ledger rows but never sends to anyone else.
2. **Drafts go to a local file, never to Slack drafts.** The path is in step 6.
3. **Never decide from a search snippet.** A search hit shows one message. Whether the operator has
   answered since is a fact about the messages after it, so read the conversation (steps 3 and 4).
4. **Never fill a gap from memory.** If a source could not be read, say which one in the header and
   list what the others found.
5. **A zero needs a positive control.** If a source returns nothing, run its read once more with a
   window that is known to hold rows (the last 14 days) and report that the control returned rows.
   An empty result that came from a failed call looks the same as a clean inbox.

## 1. Who and window

- **Operator identity.** Slack: `slack_read_user_profile` with no arguments returns the signed-in
  user, and the search tools state the user id in their description. Linear: `get_user` with
  `query: "me"`. Use these two ids everywhere below. Never hardcode either.
- **Window.** Default 72 hours back from now. An argument such as `24h` or `5d` replaces it. State the
  window in the header as UTC instants, and as a Unix timestamp for the Slack calls (`date -u -v-72H +%s`
  on macOS, `date -u -d '72 hours ago' +%s` on Linux).
- **`--source`** limits the run to one system. **`--person`** keeps only that person's items.

## 2. What counts as waiting

An item is **waiting** when all three hold:

1. The newest message in its conversation is from a human who is not the operator.
2. That message asks a question, makes a request, asks for a decision or approval, or plainly hands
   the turn to him ("over to you", "your call", "let me know").
3. The operator has not answered that ask since, in any form a person would count: a message in the
   thread, a message in the DM, or a Linear comment on the issue. A later message answers the ask only
   when it addresses it. A reply about a document does not answer an earlier request to schedule a
   call, so the earlier ask stays open. A reaction is not a reply to a question. An emoji-only answer
   from him to an FYI does close it.

**Whose comments count as his.** In Linear, comments posted from the operator's account are not all
his words. Templated automation comments (an evidence or acceptance sweep, an integration note, an
in-progress probe notice) are never replies. A comment that opens with an `actor:` line naming a lane
and cites an operator ruling is a reply made on his behalf, and counts when it addresses the ask. In
Slack, a message from his account that ends with the `(via <operator>'s agent)` footer of section 5a
was sent by an earlier run of this skill, and counts the same way.

Read the **whole tail** of the conversation, not the last line. A run of several short messages from
one person is one ask, and its wait starts at the first message of the run that the operator has not
answered.

**Excluded, with the reason stated in the output's last section:**

- Bots, apps and integrations (the search tools hide bots by default, so keep `include_bots` off),
  and any alert or notification channel (for example the notifications channel). A message from a
  person inside such a channel is still an ask.
- Pure acknowledgements: "Sure. Thank you", "ok", "thanks", an emoji or a thumbs-up, with no new ask.
- FYI links and forwards whose own text says there is nothing to act on ("nothing to work on",
  "just watching this", "for your awareness").
- The operator's own messages and anything he wrote last.
- Linear notifications that are not a question or hand-off to him: an assignment made by an
  automation, a status change, an overdue reminder. These belong to a ticket sweep, not to a reply
  check. The exception: an assignment by a person whose note asks him for something.
- An ask that was answered in another place the skill can read: a Linear ruling comment for a Slack
  ask, a channel post for a Linear question, a thread reply. Exclude it, and state where the answer
  is. When the answer sits in a different system from the question and nothing was sent back to the
  person who asked (a decision recorded on a ticket, a direct message left unanswered), list it as
  **borderline** with the words "answered in <place>, requester not told", because the person is still
  waiting from where they sit.
- A conversation the skill cannot see (a call, a huddle, an in-person talk). When the newest message
  is old and a meeting is recorded after it, exclude it and say so. When there is no sign of one,
  list it as borderline.

When a message is borderline, list it with the word "borderline" and one line of why. A missed ask
costs more than an extra line.

## 3. Slack sweep

Run searches with `slack_search_public_and_private`, `sort: "timestamp"`, `include_context: false`,
`after: <window start>`, and page with the cursor until a page ends before the window. Use the
detailed response format for the first pass, because the concise one omits the channel id the reads
below need. A detailed page of 20 can run to many thousand tokens when people post long messages, so
use `limit: 10` on busy windows.

- **A. Direct and group messages.** `filters: "is:dm"` with `channel_types: "im,mpim"`. Group the hits
  by conversation and note each conversation's channel id (the detailed format prints it). For each
  conversation, call `slack_read_channel` with that id and **no `oldest`**, `limit` 8 to 15,
  so the newest messages come first. With `oldest` set the tool returns the oldest chunk of the
  window first, and the tail you need is on a later page. The newest human message that is not the
  operator's, and everything after the operator's last message in the conversation, is the candidate
  ask.
- **Threads hide replies.** `slack_read_channel` returns top-level messages only. A reply inside a
  thread (a DM thread included) shows up in search results with a `thread_ts` in its permalink or a
  `Reply count`, and in no channel read. For every conversation, and every channel message, where a
  search hit carries one of those, call `slack_read_thread` on the parent and judge by the last reply.
  Skipping this reads a thread's last reply as a message that never happened, and reads an answered
  question as open.
- **B. Mentions in channels.** Search for the operator's user id as `<@ID>` with
  `channel_types: "public_channel,private_channel"`. For each hit, call `slack_read_thread` on the
  message (or on its `thread_ts` when it is a reply). If the operator posted in that thread after
  the mention, the mention is answered. If the mention is a top-level post, also read the channel
  from that timestamp forward with `slack_read_channel` and look for the operator's answer, since
  people often answer in the channel and not in a thread.
- **C. Threads the operator took part in.** Search `from:<@ID>` with `is:thread` in the window. For
  each thread read the replies. If the last reply is from someone else and passes step 2, it is
  waiting, even when the operator is not mentioned in it.

A mention can show up in A, B and C. Count it once, under the earliest unanswered message.

## 4. Linear sweep

- **Inbox.** `get_notifications` with `limit: 100` and `unreadOnly: false`, paging until the
  notifications are older than the window. Keep the comment, reply and mention types. Drop the
  automation-assigned, status-change and reminder types under the exclusions above, but note how many.
  A notification's subtitle holds the start of the comment, which is enough to classify and not
  enough to decide whether the operator answered.
- **Do not scan owned issues by `updatedAt`.** Lanes and automation touch most open issues many
  times a day, so `list_issues` with `assignee: "me"` and `updatedAt` in the window returns dozens of
  issues that nobody wrote to, and reading each one's comments costs more than it finds. The inbox
  already carries a notification for a comment on an issue the operator owns, created or follows.
  Use `list_issues` only as a fallback when `get_notifications` failed, capped at 25 issues.
- **Decide per issue.** For every issue with a kept notification, and for every issue a Slack ask
  names, call `list_comments` (newest first, `limit` 6) and find the operator's newest comment that
  counts as his under step 2. A comment by someone else after it is waiting when it mentions him,
  replies in a thread he wrote in, or lands on an issue he owns or created and passes step 2. If he
  has never commented, any such comment inside the window counts. A question on a ticket is often
  answered in Slack, and a Slack question in a ticket, so search the other system for the ticket id
  before listing the item.
- **Re-read the inbox at the end** (one more `get_notifications`, `limit` 10). A comment can land
  while the run is reading, and the newest ask is the one a person is most likely to be watching for.
- Comments by Linear's own bot users and by integrations are excluded like any bot.

## 5. Group, order, label

- Group by the person who is waiting. Inside a person, order by the start of their oldest unanswered
  message first. Order people by their oldest wait.
- **Wait** is now minus the start of that person's unanswered run, in hours, or days and hours past
  48 hours. State the sentence's time zone as the operator's (Eastern) when quoting clock times, and
  keep UTC in the header.
- **Label each item with the owner of the subject**, so he can see what a reply unblocks: the
  onboarding and cloud owner, the dashboard owner, or himself (delegation, platform and everything
  else). The two owners are Linear users: run
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_pillar_owner.py" onboarding` and `... dashboard`, and
  match the printed Linear user id to the person waiting. A person who is neither gets no label. If
  the command fails, drop the labels and say so in the header.

## 5a. Classify each item: AUTO or ESCALATE, and send the AUTO ones

Every waiting item gets exactly one class, with the reason written next to it. The default is
ESCALATE: an item is AUTO only when every test below holds, and any doubt, any missing basis or any
unreadable source makes it ESCALATE.

**The allowlist.** Nothing is ever sent to a person who is not on it. It holds the Slack ids of the
two pillar owners, derived on every run and never typed in or remembered:

1. Take the Linear user ids printed by `onex_pillar_owner.py onboarding` and `... dashboard` (step 5
   already runs both).
2. For each, call Linear `get_user` with that id and read the account email.
3. For each email, call `slack_search_users` and keep the one Slack user whose email equals it exactly.

The allowlist is those Slack ids. If the command fails, a pillar has no owner, `get_user` returns no
email, or the Slack lookup finds no single exact match, that owner is not on the list, and the list
may be empty. An empty list means every item is ESCALATE; say so in the header.

**AUTO needs all of these:**

1. **Recipient.** The person who is waiting is on the allowlist, and the conversation holds nobody
   else: a direct message between the operator and that person, or a group message whose every
   member is the operator or an allowlisted id. A channel, or a thread in a channel, is ESCALATE,
   because others read it. A Linear ask is ESCALATE too, because this skill writes no Linear
   comment; its draft goes to the file.
2. **Kind.** The reply is one of: a status or a fact; an answer that follows from a recorded ruling;
   routing (who or which lane owns it, where it is tracked); an acknowledgement; an agreed follow-up
   (something already agreed, now confirmed or scheduled by a lane).
3. **Basis, named.** Each statement in the reply rests on something read in this run: a ruling found
   with `python3 "${CLAUDE_PLUGIN_ROOT}/skills/lane-brief/scripts/lane_brief.py" grep <term>` and
   cited by its timestamp and lane, or a fact source (a ledger row cited by timestamp and
   lane, the output of `pr_state_local.py`, a ticket's state from Linear). A basis from memory, from
   an earlier run or from the asker's own message is no basis. Every number, id, link and name in the
   reply appears in the basis you read; a reply that states a decision the basis does not contain is
   ESCALATE.
4. **No escalate category.** None of these touches the item, as the recipient, a party to the
   conversation, or the subject of the answer:
   - a new decision, or a conflict between two rulings;
   - money, billing, contracts, or a commitment to a date;
   - anyone who is neither the operator nor an allowlisted person: the company's leadership,
     investors, customers and any outsider;
   - a review, feedback, a person, or a conflict between people;
   - a change of scope or priority for a contractor;
   - anything uncertain.
5. **Still open.** Read the conversation again immediately before sending (steps 3 and 4). If
   anyone has posted since the ask, the item is no longer the newest word: drop it from AUTO and
   classify it again from what is there now.

**Send.** One message per conversation per run, written in the voice of step 6 below, answering what was asked first. The last
line is the footer, built from the operator's own profile: `(via <first name>'s agent)`, where the
first name comes from `slack_read_user_profile` (the call step 1 already made) and is never typed in. Send it with
`slack_send_message` in the same conversation (or thread) the ask is in, and keep the permalink the
call returns.

**Log each send, right after it.** One ledger row per message, through
`/omni:ledger-msg msg --lane <this session's lane> --to operator --ticket OMN-17427`, with a body of
one line and no pipe, in this shape and with no `question=` cell (it is a report, not a decision):

```text
SENT-ON-BEHALF (RULING <ts of the ruling the ask rests on, or FACT>) to <person> <permalink>: <what was sent, one line> (basis: <ruling ts and lane, or the fact source and what it said>)
```

If the send failed, write no row, move the item to ESCALATE with the failure in its line. If the row
failed after a send went out, say so at the top of the output: that message is sent and unlogged.

## 5b. Escalate a wait that keeps going

An ESCALATE item that nobody answers must not sit in a list. The same ruling of 2026-10-16T16:30:36Z
asks for an escalation policy like the one a stuck pull request gets: a first bound that puts the item
in front of the operator, and a second bound that moves it to the person who owns its subject. The
ladder only surfaces and drafts. Nothing in it sends; every reply it drafts needs the operator's yes.

**Bounds.** Wait is the figure of step 5, measured to now.

- The first bound is 24 hours. An ESCALATE item past it is surfaced to the operator (stage 1).
- The second bound is 72 hours. An ESCALATE item past it is routed to the owner of its subject
  (stage 2) in addition to stage 1.
- An item that failed section 5a only because the send failed is an ESCALATE item and climbs the same way.
  A borderline item climbs too. An AUTO item that was sent is answered and does not climb.

**Lookback.** A 6 hour tick would never see an ask that is 30 hours old. This step therefore reads
steps 3 and 4 over a lookback of the second bound plus 24 hours (96 hours) whenever the window is
shorter, and applies the exclusions, the answered test and section 5a to what it finds exactly as for the
window. The list of section 6 still prints the window's items; the ladder uses the whole lookback.

**Memory.** Read the ladder rows first:
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/lane-brief/scripts/lane_brief.py" grep --tail 300 ESCALATION-`
An item whose permalink already has its row for a stage is not surfaced again for that stage. An item
with both rows is listed once in the morning section of step 6 as "still waiting, escalated at stage 2"
and is not pushed again.

**Stage 1: one item in the push channel.** Write the draft reply to the drafts file (step 6) in the
voice of step 6, then call `PushNotification` once for that item (one item per ask, never a digest of
several). The text states, and asks nothing:

```text
Draft reply ready for <person>, waiting <duration> on: <one line on the ask>. Draft: <drafts file path>. Link: <permalink>. Nothing is sent; it needs the operator's yes. (RULING 2026-10-16T16:30:36Z)
```

Then log it: `/omni:ledger-msg msg --lane <this session's lane> --to operator --ticket OMN-17427`, one
line, no pipe, no `question=` cell:

```text
ESCALATION-1 (RULING 2026-10-16T16:30:36Z) <person> <permalink>: waiting <hours>h past the first bound; draft at <drafts file path>, push sent, nothing sent to the person
```

If the push fails, write no row and say so at the top of the output, so the next tick tries again.

**Stage 2: route to the owner of the subject.** Use the label of step 5: run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_pillar_owner.py" onboarding` and `... dashboard`, and pick
the owner whose pillar the subject belongs to. Write a second draft in the drafts file: a short message
from the operator to that owner that names the person waiting, the link, the ask in one line and how long
it has waited, and asks the owner to answer it or say who will. Then call `PushNotification` once with the
text shape above, naming the owner and the draft, and log `ESCALATION-2` in the shape of stage 1 with the
owner in place of the person. The draft goes to the operator for approval; it is sent only after he says
yes, by him or by the session in that turn, and never by this run.
When the subject has no owner but the operator (delegation, platform and everything else), or the owner
lookup failed, there is nobody to route to: log `ESCALATION-2` anyway with "no owner, stays with the
operator" so the ladder ends, and say in the push text that the ask is past the second bound.

Both stages inherit the limits of the hard rules. The push is a statement for the operator and never a
question; a push that asks which of two things to do is refused by the question guard unless it cites the
row that already decided it.

## 6. Output

Print this, in plain English, with no table:

```
Awaiting reply, <window start UTC> to <now UTC> (<N>h). Sources read: <Slack ok|failed>, <Linear ok|failed>.
<Count> people are waiting on you, <count> items to escalate. Oldest wait: <person>, <duration>.
Sent for you this run: <count> AUTO. Allowlist: <N> of 2 pillar owners resolved.
Escalated this run: <count> to stage 1, <count> to stage 2 (section 5b).

<Person> (<label if any>), waiting <duration> on their oldest
- ESCALATE (<category or "no basis" or "doubt">): <one line: what they asked or need>. <where, as a link>. Waiting <duration>. [borderline: why]
- ...

Sent for you this run:
- <person>: <one line on what was sent>. <permalink>. Basis: <ruling ts and lane, or fact source>.

Sent on your behalf, last 24 hours:   (morning run only, see below)
- <ts UTC>: <person>: <what was sent>. <permalink>. Basis: <as logged>.

Still waiting after stage 2 (morning run only):
- <person>: <one line>. <permalink>. Waiting <duration>, escalated at stage 2 on <ts UTC>.

Left out, with the reason:
- <source and place>: <why, in a few words> (one line per kind, with a count)

Drafts: <path>
```

Each item has who, where (a Slack permalink or a Linear issue or comment url), one line on the ask
and how long they have waited. Do not paste message bodies. If nothing is waiting, say so, give the
positive-control line from rule 5, and still print the exclusions.

**The morning section.** On the first run of the day (a window of 24 hours or more, section 7) and
whenever `--sent` is passed, print the list of messages sent on the operator's behalf in the last 24
hours. It is read from the ledger, not from this run's memory, so sends by every earlier tick and by
the orchestrator itself appear:
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/lane-brief/scripts/lane_brief.py" grep --tail 200 SENT-ON-BEHALF`
Keep the `MSG` rows with `to=operator` whose leading timestamp is within 24 hours of now, oldest
first, one line each as in the layout. Say how many. If it is none, run the control
`lane_brief.py grep --tail 5 'to=operator'` and report that it returned rows, or the section is a
failed read and says so. A send whose row failed to write is added from this run's own log.
This list is the operator's daily record of what went out in his name, so print it whole and do not
shorten it.

**Drafts file.** Write one suggested reply per item to
`${CLAUDE_SCRATCHPAD:-${TMPDIR:-/tmp}}/awaiting-reply/<UTC stamp>-drafts.md`: a heading with the
person and link, the class, then the draft. An AUTO item's entry carries the text as sent and the
send time. Create the directory first. The only other writes are the sends and ledger rows of
section 5a. The ESCALATE drafts are for the operator to copy, change and send.

Voice for the drafts and for the AUTO messages, which are written as the operator:

- First person. "I", never "we" for something only he did or will do. "We" only for something the
  team really does together.
- Answer the question that was asked, first. Then the next step and who does it. If the answer needs
  a fact the skill has not read, say what it needs rather than guessing, and mark the line
  `[needs: ...]`.
- Whole sentences in an ordinary register. No clipped fragments, no stacked one-line sentences, no
  headings or bullets inside a chat reply, no emoji unless the other person used them.
- One draft per ask. Short. A decision the operator has not made is written as a question back or as
  a marker `[decision: ...]` and never as a made-up ruling.

End the run by saying how many messages it sent for him (none, when the allowlist was empty or no
item passed section 5a) and that each ESCALATE reply needs his yes.

## 7. Running on a schedule

This skill is meant to run on a schedule: a check every two hours on working days. The schedule
is the orchestrator session's canonical `awaiting-reply` tick, created by `/omni:session-start`
unit 5 (cron `17 */2 * * 1-5`, prompt `/omni:awaiting-reply 6h`) and checked byte for byte by its
loop check. For an operator running it by hand, use the 72 hour view on the first run of the day
and a 6 hour view on later runs. The reply check needs the session's Slack and Linear connections.

- Durable, outside an orchestrator session: a scheduled Claude Code routine, or a launchd timer
  that starts a headless session with these two connectors attached and the prompt
  `/omni:awaiting-reply 6h`.

A session without the connectors reports both sources as failed, which this skill prints in the
header, so a broken schedule is visible and not silent.

Whatever runs it keeps the same limits: the only sends are the AUTO ones of section 5a, to the
allowlist and nothing else; every other reply is a draft in a local file; and the list reaches the
operator as a local notification or the output itself, never as a Slack message to him. The first run
of the day, the 72 hour view, prints the 24 hour list of sends on his behalf. A session that cannot
resolve the allowlist sends nothing and says so.

## Known friction

- The escalation ladder (section 5b) reads a 96 hour lookback on every tick, including the 6 hour one,
  because an ask that is 30 hours old is outside a 6 hour window. That is more Slack and Linear reads per
  tick than the window alone; the ledger rows `ESCALATION-1` and `ESCALATION-2` stop a stage from firing
  twice, but they do not shorten the read. The ladder is prose run by a session; the node that makes it
  independent of a session is the open build of the 2026-10-16T21:02:55Z CORRECTION.

- The Slack search tools hide bots by default and return the concise form without channel ids.
  Request the detailed form, and do not turn `include_bots` on.
- Linear comments carrying the operator's name are mostly lane and automation text. Reading them as
  his replies marks open asks as answered.
- `onex_pillar_owner.py` prints a Linear user id, never a Slack id. The allowlist is therefore
  derived (Linear `get_user` email, then an exact-email Slack lookup) and is empty whenever any step
  fails. Hardcoding the two Slack ids, or matching a name, would send to the wrong person the day an
  owner changes.
- The Slack connector posts as the operator's own account, so a sent message and one he typed look
  alike. The `(via <first name>'s agent)` footer is the only mark; a run counts a message carrying it
  as his reply (section 2) and the ledger row is the record that it was an agent's.
- A reply that states a fact is only as good as the source read in the same run. The 2026-09-26 reply
  draft that approved a remediation from facts holding no such decision is the failure the basis test
  (section 5a, test 3) exists to stop; when the basis is missing the item is ESCALATE, never a softer
  AUTO.
- A search hit is one message. The skill reads the conversation before deciding, since the operator
  often answered in a place the hit does not show.
