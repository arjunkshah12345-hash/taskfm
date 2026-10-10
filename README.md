# taskfm

[![CI](https://github.com/arjunkshah12345-hash/taskfm/actions/workflows/ci.yml/badge.svg)](https://github.com/arjunkshah12345-hash/taskfm/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **Your coding agent's DJ.** taskfm reads the task your agent just started and puts on
> the matching Spotify station: deep techno for a bug hunt, synthwave for a deploy,
> lo-fi jazz for a data dive.

One small Python CLI plus a one-file agent hook. **No API keys, no daemon, no model
call**: one keyword table maps the task text to a *vibe*, [`spogo`](https://spogo.sh/)
searches Spotify for a matching playlist, and playback runs through your local Spotify
app.

```bash
taskfm start "fix the flaky websocket reconnect bug"
```

```
taskfm  debug * deep techno focus
        |> Deep Techno Focus
```

## Taste-aware stations with Qloo

Out of the box, everyone in the same vibe gets the same search results. Tell taskfm
what you like (artists, and optionally films, TV shows, books or podcasts) and it asks
[Qloo's](https://qloo.com) taste graph which artists fit **both** your taste and the
work in front of you, then plays that artist's radio station:

```toml
# ~/.config/taskfm/config.toml
[taste]
artists  = ["Bonobo", "Khruangbin", "Nils Frahm"]
movies   = ["Blade Runner 2049"]     # optional
tv_shows = ["Severance"]             # optional
```

```bash
export QLOO_API_KEY=...        # or TASKFM_TASTE="Bonobo, Khruangbin" for a one-off
taskfm start "track down the race condition in the job queue"
```

```
taskfm  debug * <artist> radio
        |> <Artist> Radio
        via Qloo: techno, because you like Bonobo, Khruangbin, Nils Frahm
```

How it decides:

1. Each name you list becomes a Qloo entity (`/search`, with `types` set to artist,
   movie, TV show, book or podcast). A film or a show is a real taste signal: Qloo's
   graph connects them to music.
2. The task's vibe picks a music genre (debug → techno, ship → synthwave,
   docs → classical, ...), resolved to a Qloo genre tag (`/v2/tags`).
3. `/v2/insights` (`filter.type=urn:entity:artist`) returns artists predicted for that
   taste (`signal.interests.entities`), steered toward the genre
   (`signal.interests.tags`). Your own seeds and anything already played are excluded
   (`filter.exclude.entities`).
4. taskfm searches Spotify for those artists' radio stations, then falls back to
   the built-in keyword stations.

Only public cultural names and a genre go to Qloo; the task text never does. IDs and
recommendations are cached for a week, and every call has a 3-second timeout. Without
a key, without taste, or when Qloo is unreachable, taskfm behaves exactly as before.
`taskfm start --json` includes a `taste` block naming the recommended artists and the
seeds behind them.

`QLOO_MODE=demo` runs the same pipeline against a small hand-written sample table, so
you can try the flow without a key. Demo results are labelled "demo data" everywhere;
they are not Qloo output.

## The web app

`taskfm serve` runs a hosted, try-it-in-the-browser version of the same pipeline:

```bash
taskfm serve --host 0.0.0.0 --port 8787     # or $PORT
```

- **Session view.** Enter your taste and a few agent prompts. For every prompt it
  shows the vibe, the station *without* Qloo (the same for everyone) next to the
  station *with* Qloo, the seeds behind it, more artists that fit, and the exact
  requests Qloo received (key redacted). Within one session, an artist is never
  picked twice.
- **Hook API.** `POST /api/hook?artists=...&movies=...` takes the same JSON a Claude
  Code `UserPromptSubmit` hook sends and returns the station, so a hosted agent can
  use taskfm without installing anything.
- `GET /healthz` reports whether the server is on live Qloo or demo data.

The Qloo key stays on the server (`QLOO_API_KEY`); without it the app runs on demo
data and says so in the header. Requests are rate limited per IP
(`TASKFM_RATE_LIMIT`, default 30 a minute).

### Deploy on Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/arjunkshah12345-hash/taskfm)

`render.yaml` defines a free Python web service. Render asks for `QLOO_API_KEY` when
you create it; leave it blank for demo mode.

## How it works

1. Your agent gets a task: a prompt, a ticket, a message in the session.
2. `taskfm` scores the text against every vibe. Concrete nouns and phrases count double
   (`css`, `readme`, `stack trace`), generic verbs count once (`fix`, `write`, `build`),
   and the highest score wins. No network, no LLM: the answer is instant and identical
   every run.
3. It searches Spotify with that vibe's queries, rotates to a fresh playlist from the
   results, and hits play via `spogo`.

## Requirements

| | |
|---|---|
| **Spotify** | A **Premium** account; free accounts can't be controlled this way |
| **spogo** | The Spotify CLI: `brew install steipete/tap/spogo` |
| **Python** | 3.11 or newer |
| **Spotify app** | On macOS, the desktop app (taskfm plays through it) |

Check the first two with `spogo --version` and `python3 --version`.

On Linux or without the desktop app, leave `engine = "auto"` in the config and taskfm
plays through **Spotify Connect** instead (phone, web player, another desktop).

## Install

Pick whichever tool you already use. All three install the `taskfm` command:

```bash
# uv (recommended)
uv tool install git+https://github.com/arjunkshah12345-hash/taskfm

# pipx
pipx install git+https://github.com/arjunkshah12345-hash/taskfm

# pip (user install)
python3 -m pip install --user git+https://github.com/arjunkshah12345-hash/taskfm
```

Working from a checkout instead:

```bash
git clone https://github.com/arjunkshah12345-hash/taskfm.git
cd taskfm
uv tool install --editable .
```

### Verify it

```bash
taskfm doctor
```

```
  [ ok ] spogo       /opt/homebrew/bin/spogo
  [ ok ] auth        1 cookie(s), no sp_dc
  [ ok ] spotify app /Applications/Spotify.app (running)
  [ ok ] engine      applescript
  [ ok ] config      ~/.config/taskfm/config.toml (using defaults)
  [ ok ] state       ~/.local/state/taskfm/state.json
  [ ok ] disabled    no
```

Anything `[fail]` or `[warn]` is explained in [Troubleshooting](#troubleshooting).

### First run

```bash
taskfm start "implement a binary search tree from scratch"
```

On macOS, if Spotify is closed taskfm opens it for you (a few seconds the first time).
After that, hook up an agent below and it happens by itself.

## Use

```bash
taskfm start "fix the flaky websocket reconnect bug"   # classify + play
taskfm start -n "refactor the billing module"          # dry run, don't touch playback
taskfm start --force "fix the flaky websocket bug"     # ignore the same-vibe cooldown
taskfm vibe "write the readme"                         # what would it pick?
taskfm vibe                                            # list every vibe
taskfm pause                                           # stop the music
taskfm status                                          # now playing + last vibe
taskfm doctor                                          # setup check
```

Prompts also come from **stdin**, including agent hook payloads. This is what makes the
adapters below one-liners:

```bash
echo '{"prompt":"review the payments pull request"}' | taskfm start
```

Machine-readable output: add `--json` to `start`, `vibe`, or `status` for a single JSON
line on stdout.

Human output is suppressed whenever stdout isn't a terminal. That is what keeps agent
hooks clean. Set `TASKFM_FORCE_STDOUT=1` to print anyway (e.g. `taskfm start ... | tee
log`), or `--json`, which always prints.

## The vibes

| vibe | sounds like | fires on |
|------|-------------|----------|
| `debug` | deep/minimal techno | bug, fix, traceback, flaky test, crash, investigate |
| `ship` | synthwave / retrowave | deploy, docker, k8s, pipeline, release, terraform |
| `data` | lo-fi jazz, chillhop | sql, pandas, dataset, embeddings, chart, analytics |
| `design` | upbeat indie | ui, css, layout, palette, landing page, animat\* |
| `docs` | calm classical | readme, documentation, changelog, article, prose |
| `review` | soft ambient | review, diff, audit, walkthrough, security |
| `focus` | deep focus / instrumental | implement, refactor, parser, algorithm, build, write |

Table order is the tie-break: when two vibes score the same, the earlier one wins, and
`focus` is the catch-all at the end.

## It stays out of the way

- **No signal → no change.** Vague or tiny prompts (`"ok"`, `"thanks"`) score below
  `min_score` and leave your music exactly where it is.
- **Same vibe → no restart.** Within `window_seconds` (default 10 min) and still
  playing, a repeat is a no-op. `taskfm start --force` overrides.
- **Kill switch.** `TASKFM_DISABLE=1` and every entry point exits quietly.

## Configuration

`~/.config/taskfm/config.toml`. Every key is optional, the defaults just work:

```toml
engine = "auto"          # auto | applescript | web | connect
min_score = 1            # score needed before music changes
window_seconds = 600     # same-vibe cooldown
fallback = "none"        # "none" = leave music alone; or a vibe name, e.g. "focus"

[playlists]              # pin a station, skips Spotify search entirely
debug = "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ"

[queries]                # replace a vibe's search terms
design = ["ambient jazz", "piano"]

[keywords]               # teach taskfm your team's vocabulary
rust = "focus"
blueprint = "design"
```

Environment variables: `TASKFM_DISABLE`, `TASKFM_ENGINE`, `TASKFM_CONFIG`,
`TASKFM_FALLBACK`, `TASKFM_FORCE_STDOUT`, `NO_COLOR`.

## Hook up your agent

Pick **one**. The CLI is identical either way. Installing two is harmless: the
same-vibe cooldown absorbs the duplicate call.

### OpenCode (automatic)

```bash
mkdir -p ~/.config/opencode/plugins
curl -o ~/.config/opencode/plugins/taskfm.js \
  https://raw.githubusercontent.com/arjunkshah12345-hash/taskfm/main/adapters/opencode/taskfm.js
```

(or `cp adapters/opencode/taskfm.js ~/.config/opencode/plugins/` from a checkout)

Every user message in a session is classified and played. Opt out with
`TASKFM_DISABLE=1`; point at a custom binary with `TASKFM_BIN`.

### Claude Code (automatic)

Add to `.claude/settings.json` (or `~/.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "taskfm start || true", "timeout": 15 }] }
    ]
  }
}
```

Claude Code pipes the prompt as JSON on stdin; `taskfm start` reads it, classifies it,
and stays silent on stdout so nothing pollutes your context.

### Any other agent (on demand)

```bash
mkdir -p ~/.agents/skills/taskfm
curl -o ~/.agents/skills/taskfm/SKILL.md \
  https://raw.githubusercontent.com/arjunkshah12345-hash/taskfm/main/adapters/skill/SKILL.md
```

The agent loads the skill when it starts a task and runs `taskfm start "<task>"` itself.
Works anywhere a `SKILL.md` is read (OpenCode, Claude Code, Cursor-compatible agents).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `taskfm: spogo not found on PATH` | `brew install steipete/tap/spogo`, then restart your shell |
| `taskfm: no Spotify playlist found` | Spotify search needs a session: `spogo auth import --browser chrome` |
| `auth` shows `no sp_dc` but search works | Expected on a fresh machine; playback uses the local app anyway |
| `the Spotify app is not available` | Install the Spotify desktop app, or set `engine = "auto"` for Connect |
| Playback starts on the wrong device | `spogo device list` then `spogo device set "<name>"` |
| `429` / rate-limit errors | Too many web calls; wait a moment, the macOS app engine avoids them |
| Nothing happens on my prompt | Correct: the prompt scored below `min_score`. Use `taskfm start --force` or set `fallback = "focus"` |
| Music keeps changing mid-task | That's the hook working. `TASKFM_DISABLE=1`, or raise `window_seconds` |

## Development

```bash
git clone https://github.com/arjunkshah12345-hash/taskfm.git
cd taskfm
uv sync                      # installs pytest + ruff (dev group)
uv run pytest                # unit tests, no Spotify needed
uv run ruff check .          # lint
uv run ruff format --check . # format
```

The classifier is the whole product: `taskfm/vibes.py` plus `tests/test_vibes.py`.
Playback (`taskfm/player.py`) shells out to `spogo`; nothing else is talked to.

## Uninstall

```bash
rm -rf ~/.config/opencode/plugins/taskfm.js ~/.agents/skills/taskfm
uv tool uninstall taskfm
```

## License

MIT. See [LICENSE](LICENSE).
