# <Fault name>

**Status:** open — recurrence watch | resolved | monitoring

## The one-line answer

<One or two sentences: what is actually wrong, how to tell, and the single
command or action that recovers it. This is the part someone reads at
2am — put the fix before the explanation.>

## How to recognise it

| Signal | <Faulty state> | Healthy |
|---|---|---|
| <thing you can check> | | |
| <thing you can check> | | |

## Incident record: <date>

<Host, image/version, config in effect at the time. A UTC timeline of what
happened, in the order it was observed — not the order it was understood.
Include what forensic data was captured and where (see the
`incident-capture` skill), and what was not captured and why, if relevant.>

### <HH:MM UTC> — <short description>

- <what the logs/metrics/kernel log showed>
- <what automatic recovery did or did not do>

## Working hypothesis

<What is believed to be the root cause, with evidence and links to
upstream issues if any. Say plainly if this is not confirmed.>

## Why the cluster did not heal itself

<Which safety net should have caught this and did not — a liveness probe
that doesn't actually prove the failure mode, a timeout that doesn't
exist, an alert that isn't wired up yet. Be specific: this section is what
turns into the alerting/watchdog follow-up work.>

## Follow-ups

- [ ] <action item>
- [ ] <action item>

Each item above is mirrored as a GitHub issue labelled `follow-up`, so a
follow-up cannot get lost in prose the way this document's predecessors
sometimes did — track completion on the issue, not by editing this
checkbox after the fact.

Related: <links to plans, other troubleshooting docs, or upstream issues>
