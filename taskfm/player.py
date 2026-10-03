"""Thin wrapper around the `spogo` CLI.

spogo talks to Spotify's web API (search) and can drive playback through several
engines. On macOS the `applescript` engine runs against the local Spotify app, so
playback needs no session cookies at all - only search does.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

SPOGO = "spogo"
SPOTIFY_APP_PATHS = (
    Path("/Applications/Spotify.app"),
    Path.home() / "Applications" / "Spotify.app",
)


class PlayerError(RuntimeError):
    """spogo missing, failing, or returning something we can't use."""


def spogo(
    args: list[str],
    *,
    engine: str | None = None,
    as_json: bool = False,
    timeout: float = 25.0,
) -> str:
    cmd = [SPOGO, *args]
    if as_json:
        cmd.append("--json")
    if engine:
        cmd += ["--engine", engine]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise PlayerError(
            "spogo not found on PATH. Install it first (see README, Requirements)."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PlayerError(f"spogo timed out after {timeout:.0f}s: {' '.join(cmd)}") from exc

    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip()
        raise PlayerError(message or f"spogo exited {proc.returncode}")
    return proc.stdout


def spogo_json(
    args: list[str],
    *,
    engine: str | None = None,
    timeout: float = 25.0,
) -> dict:
    raw = spogo(args, engine=engine, as_json=True, timeout=timeout)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PlayerError(f"spogo returned invalid JSON: {raw[:200]}") from exc
    if not isinstance(data, dict):
        raise PlayerError("spogo returned unexpected JSON")
    return data


def search_playlists(query: str, *, limit: int = 5) -> list[dict]:
    """Search Spotify playlists. Returns [{id, uri, name, url}, ...]."""
    data = spogo_json(["search", "playlist", query, "--limit", str(limit)])
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and i.get("uri")]


def spotify_app_path() -> Path | None:
    for path in SPOTIFY_APP_PATHS:
        if path.exists():
            return path
    return None


def spotify_running() -> bool:
    if shutil.which("pgrep") is None:
        return False
    try:
        return (
            subprocess.run(["pgrep", "-x", "Spotify"], capture_output=True, check=False).returncode
            == 0
        )
    except OSError:
        return False


def ensure_spotify_running(timeout: float = 20.0) -> bool:
    """Launch the Spotify desktop app if needed (macOS applescript engine only)."""
    if spotify_running():
        return True
    app = spotify_app_path()
    if app is None or shutil.which("open") is None:
        return False
    subprocess.run(["open", "-a", str(app)], capture_output=True, check=False)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if spotify_running():
            return True
        time.sleep(0.5)
    return spotify_running()


def resolve_engine(preference: str) -> str:
    """Turn a config preference into a concrete spogo engine."""
    if preference and preference != "auto":
        return preference
    if sys.platform == "darwin" and spotify_app_path() is not None:
        return "applescript"
    return "auto"


def play(uri: str, engine: str) -> None:
    if engine == "applescript" and not ensure_spotify_running():
        raise PlayerError(
            'the Spotify app is not available; set `engine = "auto"` in config '
            "to play through Spotify Connect instead"
        )
    try:
        spogo(["play", uri], engine=engine)
    except PlayerError:
        if engine == "auto":
            raise
        # Web/Connect can be flaky (rate limits, expired cookies) - try it anyway.
        spogo(["play", uri], engine="auto")


def status(engine: str) -> dict:
    try:
        if engine == "applescript" and not ensure_spotify_running(timeout=5):
            raise PlayerError("spotify app not running")
        return spogo_json(["status"], engine=engine, timeout=15)
    except PlayerError:
        if engine == "applescript":
            return spogo_json(["status"], engine="auto", timeout=15)
        raise


def is_playing(engine: str) -> bool:
    try:
        return bool(status(engine).get("is_playing"))
    except PlayerError:
        return False


def pause(engine: str) -> None:
    try:
        spogo(["pause"], engine=engine, timeout=15)
    except PlayerError:
        if engine == "auto":
            raise
        spogo(["pause"], engine="auto", timeout=15)


def auth_summary() -> str:
    try:
        data = spogo_json(["auth", "status"], timeout=15)
    except PlayerError as exc:
        return f"error: {exc}"
    count = data.get("cookie_count", 0)
    parts = [f"{count} cookie(s)"]
    parts.append("sp_dc ok" if data.get("has_sp_dc") else "no sp_dc")
    return ", ".join(parts)
