---
name: taskfm
description: Start Spotify music matched to the coding task you are about to begin. Use when you start a new task from a user prompt, move to a different kind of work, or the user asks you to put on music or set the vibe.
---

## What I do

`taskfm` reads a task description, works out what kind of work it is (debugging,
shipping, data, design, docs, review, deep focus) and starts a Spotify station to
match. It is a local CLI - no API keys, no network from you, no output to read.

## When to use me

- The user gives you a **new task** - call once, right when you take it on.
- The work **changes kind** mid-session (you were writing code, now you're reviewing a
  PR) - call again with the new task.

Do **not** call it for every tool call, every file edit, or every reply. One call per
new task.

## How

```bash
taskfm start "fix the flaky websocket reconnect bug"
```

That's the whole integration. Pass the task in your own words. The command prints
nothing when your stdout is not a terminal, exits `0` on a no-op, and never blocks on
your behalf for long.

If you only want to know what it would pick, without touching playback:

```bash
taskfm vibe "write the readme"
```

## Rules

- **If `taskfm` is not on PATH, do nothing.** Never install it, never treat a failure
  as a task error. Music is a nicety; the task is the job.
- **Exit code 0 with no output means "left your music alone"** - a vague or tiny
  prompt scored below threshold. That is correct behavior, not a failure.
- **Never retry.** A failure stays a failure; move on with the actual work.
- If the user says stop the music / pause: `taskfm pause`.

## Commands

| command | purpose |
|---------|---------|
| `taskfm start "<task>"` | classify + play |
| `taskfm start -n "<task>"` | dry run (resolve the station, don't play) |
| `taskfm vibe "<task>"` | show the classification only |
| `taskfm pause` | pause playback |
| `taskfm status` | now playing + last vibe |
| `taskfm doctor` | setup check |

Useful flags: `--force` (ignore the same-vibe cooldown), `--json` (one JSON line),
`-q` (silent).

## Configuration

`~/.config/taskfm/config.toml` may pin playlists, swap search queries, or add keywords.
Environment: `TASKFM_DISABLE=1` disables every entry point - if that is set, do not
call `taskfm` at all.
