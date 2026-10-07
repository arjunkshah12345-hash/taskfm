# taskfm × Qloo — Qloo Agentic Hackathon

> Devpost fields below. Demo video must show `taskfm start "<task>"` picking a station from Qloo recommendations, with the "via Qloo" line. Requirement: integrate the Qloo API, integrated into an existing agent-side tool.

**Tagline:** Your coding agent's DJ — now it picks music from *your* taste, grounded in Qloo's taste graph, matched to the task it just started.

**Repo:** https://github.com/arjunkshah12345-hash/taskfm

---

## Inspiration
taskfm reads the task your coding agent just started and plays a matching Spotify station — techno for a bug hunt, synthwave for a deploy. But everyone in the same vibe got the same generic search. Qloo's taste graph lets it start from *your* taste and recommend artists that fit both what you like and the kind of work in front of you.

## What it does
Tell taskfm a few artists you like. When your agent starts a task, taskfm:
1. Classifies the task into a vibe (debug, ship, data, design, docs, review, focus).
2. Asks **Qloo** which artists a listener with your taste would like, steered toward that vibe's genre.
3. Plays that artist's radio station on Spotify.

```
taskfm  debug * Four Tet radio
        |> Four Tet Radio
        via Qloo: techno, because you like Bonobo, Khruangbin, Nils Frahm
```

If Qloo is unavailable, it falls back silently to its built-in keyword stations — the agent is never blocked.

## How we used Qloo
- **`/search`** resolves your artists to Qloo entities.
- **`/v2/tags`** resolves the vibe's genre to a Qloo music-genre tag.
- **`/v2/insights`** (`filter.type=urn:entity:artist`, `signal.interests.entities` = your taste, `signal.interests.tags` = the genre) returns artists predicted for you, steered to the task's mood. Artists you already listed are excluded.

taskfm is an agent-side tool (it runs from a coding agent's hook), and Qloo is integrated into it in code (`taskfm/qloo.py`) — an existing agent tool made taste-aware, matching the "integrate the Qloo API into an existing agent" path.

## Built during the hackathon
taskfm existed before as a keyword→vibe→Spotify tool. **New for this hackathon:** the entire Qloo integration — taste config, the search→tags→insights pipeline, a week-long cache, 3-second timeouts, a silent fallback, a `taste` block in `--json` output, and 6 new tests (32 total passing).

## How to run / test
`uv run taskfm start "track down the race condition in the job queue"` with `QLOO_API_KEY` set and `[taste] artists = [...]` in `~/.config/taskfm/config.toml` (or `TASKFM_TASTE="Bonobo, Khruangbin"`). `pytest` → 32 passing, including the Qloo pipeline against a fake API (signals sent, cache hit, no-tag fallback, error fallback).

## Tech
Python (stdlib only — zero dependencies), Qloo Insights API, Spotify via spogo.

## Challenges
Keeping taskfm instant and dependency-free while adding a network call: everything is cached and time-boxed, and any Qloo hiccup falls back to the original behavior so a coding hook never stalls on music.

## What's next
Per-vibe taste profiles, feedback ("skip" teaches taste), and Qloo-grounded picks for focus playlists beyond single-artist radio.
