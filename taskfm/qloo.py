"""Taste-aware stations from Qloo's taste graph.

Without Qloo, every developer in the same vibe hears the same search results.
With it, taskfm starts from the artists *you* like and asks Qloo which artists
fit both your taste and the genre of the work in front of you:

    you like Bonobo + Khruangbin, you start a bug hunt (techno)
      -> Qloo: Four Tet, Floating Points, Caribou ...
      -> Spotify: "Four Tet radio"

Every call is optional and bounded. Missing key, no taste set, a slow or
failing API: taskfm quietly falls back to its built-in keyword stations, so a
hook never stalls a prompt.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from taskfm.config import state_path

DEFAULT_BASE_URL = "https://hackathon.api.qloo.com"
TIMEOUT_SECONDS = 3.0
CACHE_TTL_SECONDS = 7 * 24 * 3600

# The music genre each vibe leans toward, used as a Qloo tag signal.
VIBE_GENRES: dict[str, str] = {
    "debug": "techno",
    "ship": "synthwave",
    "data": "jazz",
    "design": "indie pop",
    "docs": "classical",
    "review": "ambient",
    "focus": "electronic",
}


class QlooError(Exception):
    pass


@dataclass
class Recommendation:
    artists: list[str]
    seeds: list[str]
    genre: str | None
    tag_id: str | None = None
    notes: list[str] = field(default_factory=list)


def api_key() -> str | None:
    return os.environ.get("QLOO_API_KEY") or None


def base_url() -> str:
    return os.environ.get("QLOO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _get(path: str, params: dict[str, str], *, opener=urllib.request.urlopen) -> dict:
    url = f"{base_url()}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"X-Api-Key": api_key() or "", "Accept": "application/json"}
    )
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise QlooError(f"Qloo {exc.code} on {path}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise QlooError(f"Qloo unreachable: {exc}") from exc


# ---- a small on-disk cache: artist and tag IDs barely change -------------------


def _cache_path() -> Path:
    return state_path().with_name("qloo-cache.json")


def _cache_load() -> dict:
    try:
        data = json.loads(_cache_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_save(cache: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2) + "\n")
        tmp.replace(path)
    except OSError:
        pass


def _cached(cache: dict, key: str, compute):
    hit = cache.get(key)
    if isinstance(hit, dict) and time.time() - hit.get("at", 0) < CACHE_TTL_SECONDS:
        return hit.get("value")
    value = compute()
    cache[key] = {"value": value, "at": time.time()}
    return value


# ---- Qloo lookups ----------------------------------------------------------------------


def resolve_artist(name: str, *, opener=urllib.request.urlopen) -> str | None:
    """Artist name -> Qloo entity ID."""
    data = _get(
        "/search",
        {"query": name, "types": "urn:entity:artist", "take": "1"},
        opener=opener,
    )
    results = data.get("results") or []
    return results[0].get("entity_id") if results else None


def resolve_genre_tag(genre: str, *, opener=urllib.request.urlopen) -> str | None:
    """Genre word -> Qloo music-genre tag ID."""
    data = _get(
        "/v2/tags",
        {"filter.query": genre, "filter.tag.types": "urn:tag:genre:music", "take": "1"},
        opener=opener,
    )
    tags = (data.get("results") or {}).get("tags") or []
    return tags[0].get("id") if tags else None


def artist_insights(
    seed_ids: list[str], tag_id: str | None, *, take: int = 10, opener=urllib.request.urlopen
) -> list[str]:
    """Artists Qloo predicts this listener will like, steered toward a genre."""
    params = {
        "filter.type": "urn:entity:artist",
        "signal.interests.entities": ",".join(seed_ids),
        "take": str(take),
    }
    if tag_id:
        params["signal.interests.tags"] = tag_id
    data = _get("/v2/insights", params, opener=opener)
    entities = (data.get("results") or {}).get("entities") or []
    return [str(e["name"]) for e in entities if isinstance(e, dict) and e.get("name")]


def recommend(vibe: str, taste: list[str], *, opener=urllib.request.urlopen) -> Recommendation:
    """Artists for this vibe and this listener. Raises QlooError if Qloo can't help."""
    if not api_key():
        raise QlooError("QLOO_API_KEY is not set")
    if not taste:
        raise QlooError("no taste artists configured")

    cache = _cache_load()
    try:
        seeds: list[str] = []
        notes: list[str] = []
        for name in taste[:5]:
            entity = _cached(
                cache, f"artist:{name.lower()}", lambda n=name: resolve_artist(n, opener=opener)
            )
            if entity:
                seeds.append(entity)
            else:
                notes.append(f"Qloo doesn't know {name!r}")
        if not seeds:
            raise QlooError("none of your taste artists were found on Qloo")

        genre = VIBE_GENRES.get(vibe)
        tag_id = None
        if genre:
            try:
                tag_id = _cached(
                    cache, f"tag:{genre}", lambda: resolve_genre_tag(genre, opener=opener)
                )
            except QlooError as exc:
                notes.append(f"genre tag lookup failed ({exc}); using taste alone")

        key = f"insights:{vibe}:{','.join(sorted(seeds))}"
        artists = _cached(cache, key, lambda: artist_insights(seeds, tag_id, opener=opener))
    finally:
        _cache_save(cache)

    taste_lower = {t.lower() for t in taste}
    fresh = [a for a in artists or [] if a.lower() not in taste_lower]
    if not fresh:
        raise QlooError("Qloo returned no new artists")
    return Recommendation(artists=fresh, seeds=taste, genre=genre, tag_id=tag_id, notes=notes)


def station_queries(rec: Recommendation, limit: int = 3) -> list[str]:
    return [f"{artist} radio" for artist in rec.artists[:limit]]
