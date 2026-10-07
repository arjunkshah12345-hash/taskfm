"""Configuration + state paths. Everything has a working default."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def config_path() -> Path:
    override = os.environ.get("TASKFM_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "taskfm" / "config.toml"


def state_path() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / "taskfm" / "state.json"


@dataclass
class Config:
    engine: str = "auto"
    min_score: float = 1.0
    fallback: str = "none"
    window_seconds: int = 600
    queries: dict[str, list[str]] = field(default_factory=dict)
    playlists: dict[str, str] = field(default_factory=dict)
    keywords: dict[str, str] = field(default_factory=dict)
    taste: list[str] = field(default_factory=list)
    disabled: bool = False
    path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> Config:
        cfg = cls()
        path = config_path()
        cfg.path = path

        if path.is_file():
            try:
                with path.open("rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                cfg.warnings.append(f"could not read {path}: {exc}")
                data = {}
            cfg._apply(data)

        # Environment wins over file, so a hook can flip settings per-session.
        if os.environ.get("TASKFM_DISABLE"):
            cfg.disabled = True
        if os.environ.get("TASKFM_ENGINE"):
            cfg.engine = os.environ["TASKFM_ENGINE"]
        if os.environ.get("TASKFM_FALLBACK"):
            cfg.fallback = os.environ["TASKFM_FALLBACK"]
        if os.environ.get("TASKFM_TASTE"):
            cfg.taste = [a.strip() for a in os.environ["TASKFM_TASTE"].split(",") if a.strip()]
        return cfg

    def _apply(self, data: dict) -> None:
        for key in ("engine", "fallback"):
            if isinstance(data.get(key), str):
                setattr(self, key, data[key])
        if isinstance(data.get("min_score"), (int, float)):
            self.min_score = float(data["min_score"])
        if isinstance(data.get("window_seconds"), int):
            self.window_seconds = int(data["window_seconds"])

        queries = data.get("queries")
        if isinstance(queries, dict):
            for vibe, value in queries.items():
                if isinstance(value, list):
                    self.queries[str(vibe)] = [str(v) for v in value]
                elif isinstance(value, str):
                    self.queries[str(vibe)] = [value]

        playlists = data.get("playlists")
        if isinstance(playlists, dict):
            self.playlists.update({str(k): str(v) for k, v in playlists.items()})

        taste = data.get("taste")
        if isinstance(taste, dict):
            taste = taste.get("artists")
        if isinstance(taste, list):
            self.taste = [str(a).strip() for a in taste if str(a).strip()]

        keywords = data.get("keywords")
        if isinstance(keywords, dict):
            self.keywords.update({str(k).lower(): str(v) for k, v in keywords.items()})


@dataclass
class State:
    last_vibe: str = ""
    last_uri: str = ""
    last_name: str = ""
    last_at: float = 0.0
    cursor: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls) -> State:
        path = state_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        cursor = data.get("cursor")
        return cls(
            last_vibe=str(data.get("last_vibe", "")),
            last_uri=str(data.get("last_uri", "")),
            last_name=str(data.get("last_name", "")),
            last_at=float(data.get("last_at", 0.0) or 0.0),
            cursor={str(k): int(v) for k, v in cursor.items()} if isinstance(cursor, dict) else {},
        )

    def save(self) -> None:
        path = state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.__dict__, indent=2) + "\n")
            tmp.replace(path)
        except OSError:
            # State is a nicety; never fail a playback over it.
            pass
