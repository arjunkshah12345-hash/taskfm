"""taskfm command line: start / vibe / pause / status / doctor."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from shutil import which

from taskfm import __version__, qloo
from taskfm.config import Config, State, config_path, state_path
from taskfm.player import (
    PlayerError,
    auth_summary,
    is_playing,
    pause,
    play,
    resolve_engine,
    search_playlists,
    spotify_app_path,
    spotify_running,
    status,
)
from taskfm.vibes import VIBES, classify

DIM, BOLD, CYAN, GREEN, RESET = "\033[2m", "\033[1m", "\033[36m", "\033[32m", "\033[0m"
PREFIX = "taskfm  "
INDENT = " " * len(PREFIX)
STDIN_KEYS = ("prompt", "message", "content", "text", "input")


def _paint(text: str, *codes: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return "".join(codes) + text + RESET


def _out(lines: list[str], quiet: bool = False) -> None:
    if quiet or (not sys.stdout.isatty() and os.environ.get("TASKFM_FORCE_STDOUT") is None):
        return
    for line in lines:
        print(line)


def extract_prompt(data: str) -> str:
    """Read a prompt from stdin: plain text, or a hook payload like {"prompt": ...}."""
    text = data.strip()
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            for key in STDIN_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return text


def _prompt(positional: list[str]) -> str:
    if positional:
        return " ".join(positional).strip()
    if sys.stdin.isatty():
        return ""
    try:
        return extract_prompt(sys.stdin.read())
    except (OSError, ValueError):
        return ""


def _queries_for(cfg: Config, vibe_name: str, fallback: tuple[str, ...]) -> list[str]:
    custom = cfg.queries.get(vibe_name)
    return list(custom) if custom else list(fallback)


def _pick_playlist(
    queries: list[str], state: State, vibe_name: str, limit: int = 5
) -> tuple[dict | None, str]:
    """Search Spotify for a playlist, rotating through results run over run."""
    for query in queries[:3]:
        try:
            items = search_playlists(query, limit=limit)
        except PlayerError:
            continue
        if items:
            index = state.cursor.get(vibe_name, 0) % len(items)
            state.cursor[vibe_name] = (index + 1) % len(items)
            return items[index], query
    return None, ""


def cmd_start(args: argparse.Namespace) -> int:
    cfg = Config.load()
    for warning in cfg.warnings:
        print(f"taskfm: {warning}", file=sys.stderr)

    if cfg.disabled:
        _out([PREFIX + _paint("disabled", DIM) + " (TASKFM_DISABLE)"], args.quiet)
        return 0

    prompt = _prompt(args.text)
    if not prompt:
        print(
            "taskfm: no prompt given - pass text, pipe text, or pipe hook JSON on stdin",
            file=sys.stderr,
        )
        return 2

    match = classify(
        prompt,
        min_score=cfg.min_score,
        extra_keywords=cfg.keywords,
        fallback=cfg.fallback,
    )
    if match.vibe is None:
        _out(
            [PREFIX + _paint("no signal", DIM) + " - leaving music alone"],
            args.quiet,
        )
        if args.json:
            print(json.dumps({"action": "skip", "reason": match.reason, "score": match.score}))
        return 0

    vibe = match.vibe
    queries = _queries_for(cfg, vibe.name, vibe.queries)
    engine = resolve_engine(args.engine or cfg.engine)
    state = State.load()

    if (
        not args.force
        and state.last_vibe == vibe.name
        and (time.time() - state.last_at) < cfg.window_seconds
        and is_playing(engine)
    ):
        _out(
            [PREFIX + _paint("already in " + vibe.name, DIM) + " - not restarting"],
            args.quiet,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "action": "skip",
                        "reason": "same vibe in window",
                        "vibe": vibe.name,
                        "name": state.last_name,
                        "uri": state.last_uri,
                    }
                )
            )
        return 0

    taste = _taste_for(cfg, vibe.name, args.quiet)
    pinned = cfg.playlists.get(vibe.name)
    if pinned:
        item, query = {"uri": pinned, "name": pinned}, "(pinned)"
    else:
        item, query = _pick_playlist(
            (qloo.station_queries(taste) if taste else []) + queries, state, vibe.name
        )

    if item is None:
        print(
            f"taskfm: no Spotify playlist found for vibe {vibe.name!r} "
            f"(tried {', '.join(queries[:3])})",
            file=sys.stderr,
        )
        return 1

    uri = str(item.get("uri", ""))
    name = str(item.get("name", uri)).strip() or uri
    payload = {
        "vibe": vibe.name,
        "score": match.score,
        "query": query,
        "name": name,
        "uri": uri,
        "engine": engine,
    }
    if taste and query in qloo.station_queries(taste):
        payload["taste"] = {
            "source": taste.source,
            "because_you_like": taste.seeds,
            "genre": taste.genre,
            "recommended": taste.artists[:5],
        }

    if args.dry_run:
        if args.json:
            print(json.dumps({**payload, "action": "dry-run"}))
        else:
            _out(
                _start_lines(payload, dry_run=True),
                args.quiet,
            )
        return 0

    play(uri, engine)

    state.last_vibe = vibe.name
    state.last_uri = uri
    state.last_name = name
    state.last_at = time.time()
    state.save()

    if args.json:
        print(json.dumps({**payload, "action": "play"}))
    else:
        _out(_start_lines(payload, dry_run=False), args.quiet)
    return 0


def _taste_for(cfg: Config, vibe_name: str, quiet: bool) -> qloo.Recommendation | None:
    """Qloo's picks for this listener and vibe, or None to use the keyword stations."""
    if not (cfg.taste or cfg.taste_extra) or not (qloo.api_key() or qloo.demo_mode()):
        return None
    try:
        return qloo.recommend(vibe_name, cfg.taste, extra_taste=cfg.taste_extra)
    except qloo.QlooError as exc:
        if not quiet:
            print(f"taskfm: {exc} - using built-in stations", file=sys.stderr)
        return None


def _start_lines(payload: dict, *, dry_run: bool) -> list[str]:
    query = _paint(str(payload["query"]), DIM)
    name = _paint(str(payload["name"]), BOLD)
    head = PREFIX + _paint(str(payload["vibe"]), CYAN) + " " + _paint("*", DIM) + " " + query
    if dry_run:
        head += _paint("  (dry run)", DIM)
        name += _paint("  (would play)", DIM)
    lines = [head, INDENT + _paint("|>", GREEN) + " " + name]
    taste = payload.get("taste")
    if taste:
        lines.append(
            INDENT
            + _paint(
                f"via {'Qloo' if taste['source'] == 'qloo' else 'demo data'}: "
                f"{taste['genre'] or 'your taste'}, because you like ",
                DIM,
            )
            + ", ".join(taste["because_you_like"][:3])
        )
    return lines


def cmd_vibe(args: argparse.Namespace) -> int:
    cfg = Config.load()
    prompt = _prompt(args.text)

    if not prompt:
        # No prompt = describe the menu.
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "vibe": v.name,
                            "blurb": v.blurb,
                            "queries": list(v.queries),
                        }
                        for v in VIBES
                    ]
                )
            )
        else:
            for vibe in VIBES:
                print(f"{PREFIX}{_paint(vibe.name, CYAN)} {vibe.blurb}")
                print(f"{INDENT}{' | '.join(vibe.queries)}")
        return 0

    match = classify(
        prompt,
        min_score=cfg.min_score,
        extra_keywords=cfg.keywords,
        fallback=cfg.fallback,
    )
    if match.vibe is None:
        if args.json:
            print(json.dumps({"vibe": None, "score": match.score, "reason": match.reason}))
        else:
            print(PREFIX + _paint("no signal", DIM) + " - leaving music alone")
        return 0

    vibe = match.vibe
    if args.json:
        print(
            json.dumps(
                {
                    "vibe": vibe.name,
                    "blurb": vibe.blurb,
                    "score": match.score,
                    "reason": match.reason,
                    "matches": [{"keyword": k, "weight": w} for k, w in match.matches],
                    "queries": _queries_for(cfg, vibe.name, vibe.queries),
                }
            )
        )
        return 0

    hits = ", ".join(f"{k}({w:g})" for k, w in match.matches) or "-"
    print(PREFIX + _paint(vibe.name, CYAN) + f"  score {match.score:g}  {vibe.blurb}")
    print(INDENT + _paint("matches ", DIM) + hits)
    print(INDENT + _paint("queries ", DIM) + " | ".join(_queries_for(cfg, vibe.name, vibe.queries)))
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    cfg = Config.load()
    engine = resolve_engine(cfg.engine)
    pause(engine)
    _out([PREFIX + _paint("paused", DIM)], args.quiet)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = Config.load()
    engine = resolve_engine(cfg.engine)
    state = State.load()
    info = status(engine)
    item = info.get("item") or {}
    artists = ", ".join(item.get("artists") or [])
    title = item.get("name") or item.get("uri") or "unknown track"
    playing = "playing" if info.get("is_playing") else "paused"

    if args.json:
        print(
            json.dumps(
                {
                    "state": playing,
                    "track": title,
                    "artists": artists,
                    "engine": engine,
                    "last_vibe": state.last_vibe,
                    "last_at": state.last_at,
                }
            )
        )
        return 0

    suffix = f" - {artists}" if artists else ""
    print(PREFIX + _paint(playing, CYAN) + f" {title}{suffix}")
    if state.last_vibe:
        age = int(time.time() - state.last_at)
        print(INDENT + _paint("last vibe ", DIM) + f"{state.last_vibe} ({_ago(age)})")
    print(INDENT + _paint("engine ", DIM) + engine)
    return 0


def _ago(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = Config.load()
    engine = resolve_engine(cfg.engine)
    ok, warn, bad = "[ ok ]", "[warn]", "[fail]"

    checks: list[tuple[str, str, str]] = []

    spogo_bin = which("spogo")
    checks.append(("spogo", spogo_bin or "not on PATH", ok if spogo_bin else bad))
    checks.append(("auth", auth_summary() if spogo_bin else "skipped", ok if spogo_bin else bad))

    app = spotify_app_path()
    if app is None:
        checks.append(("spotify app", "not found", warn))
    else:
        state = "running" if spotify_running() else "installed, not running"
        checks.append(("spotify app", f"{app} ({state})", ok))

    checks.append(("engine", engine, ok))
    cfg_state = "using defaults" if not cfg.path or not cfg.path.is_file() else "loaded"
    checks.append(("config", f"{cfg.path or config_path()} ({cfg_state})", ok))
    checks.append(("state", str(state_path()), ok))
    checks.append(("disabled", "yes" if cfg.disabled else "no", warn if cfg.disabled else ok))

    for name, detail, mark in checks:
        color = {"[ ok ]": GREEN, "[warn]": DIM, "[fail]": "\033[31m"}.get(mark, "")
        print(f"  {_paint(mark, color)} {name:<11} {detail}")

    for warning in cfg.warnings:
        print(f"  {_paint('[warn]', DIM)} {warning}")

    return 0 if spogo_bin else 1


def cmd_serve(args: argparse.Namespace) -> int:
    from taskfm import web

    port = args.port or int(os.environ.get("PORT", "8787"))
    web.serve(args.host, port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taskfm",
        description="Play Spotify music matched to the task your coding agent just started.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"taskfm {__version__}")
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="classify a task prompt and start the matching music")
    start.add_argument("text", nargs="*", help="task prompt (or pipe it on stdin)")
    start.add_argument("-q", "--quiet", action="store_true", help="print nothing")
    start.add_argument("-f", "--force", action="store_true", help="ignore the same-vibe window")
    start.add_argument("-n", "--dry-run", action="store_true", help="resolve but do not play")
    start.add_argument("--json", action="store_true", help="print one JSON line")
    start.add_argument(
        "--engine",
        choices=["auto", "web", "connect", "applescript"],
        help="playback engine (default: config, then auto)",
    )
    start.set_defaults(func=cmd_start)

    vibe = sub.add_parser("vibe", help="show the vibe for a prompt (or list all vibes)")
    vibe.add_argument("text", nargs="*", help="task prompt (or pipe it on stdin)")
    vibe.add_argument("--json", action="store_true", help="print JSON")
    vibe.set_defaults(func=cmd_vibe)

    pause_p = sub.add_parser("pause", help="pause playback")
    pause_p.add_argument("-q", "--quiet", action="store_true")
    pause_p.set_defaults(func=cmd_pause)

    status_p = sub.add_parser("status", help="show playback + last vibe")
    status_p.add_argument("--json", action="store_true")
    status_p.set_defaults(func=cmd_status)

    doctor = sub.add_parser("doctor", help="check spogo, Spotify and config")
    doctor.set_defaults(func=cmd_doctor)

    serve = sub.add_parser("serve", help="run the taskfm web app and hook API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=None, help="default: $PORT or 8787")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except PlayerError as exc:
        print(f"taskfm: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
