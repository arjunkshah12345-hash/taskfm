"""Taste-aware stations from Qloo's taste graph.

Without Qloo, every developer in the same vibe hears the same search results.
With it, taskfm starts from what *you* like (artists, and optionally films,
shows, books and podcasts) and asks Qloo which artists fit both your taste and
the genre of the work in front of you:

    you like Bonobo + Blade Runner 2049, you start a bug hunt (techno)
      -> Qloo: artists predicted for that taste, steered toward techno
      -> Spotify: "<artist> radio"

Only public cultural names and a genre go to Qloo. The task text itself never
leaves your machine (or the taskfm server).

Every call is optional and bounded. Missing key, no taste set, a slow or
failing API: taskfm quietly falls back to its built-in keyword stations, so a
hook never stalls a prompt.

QLOO_MODE=demo swaps the network for a small hand-written sample table so the
whole pipeline can be tried without a key. Demo results are labelled as such
and are not Qloo data.
"""

from __future__ import annotations

import json
import os
import re
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
MAX_SEEDS_PER_TYPE = 5

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

# Taste categories taskfm accepts, and the Qloo entity type for each.
SEED_TYPES: dict[str, str] = {
    "artists": "urn:entity:artist",
    "movies": "urn:entity:movie",
    "tv_shows": "urn:entity:tv_show",
    "books": "urn:entity:book",
    "podcasts": "urn:entity:podcast",
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
    picks: list[dict] = field(default_factory=list)  # name, entity_id, affinity
    seed_entities: list[dict] = field(default_factory=list)  # name, kind, entity_id
    trace: list[dict] = field(default_factory=list)  # redacted requests, in order
    source: str = "qloo"  # "qloo" or "demo"


def api_key() -> str | None:
    return os.environ.get("QLOO_API_KEY") or None


def demo_mode() -> bool:
    return os.environ.get("QLOO_MODE", "").lower() == "demo"


def base_url() -> str:
    return os.environ.get("QLOO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _get(path: str, params: dict[str, str], *, opener=urllib.request.urlopen, trace=None) -> dict:
    if trace is not None:
        # The key travels in a header and is never recorded.
        trace.append({"method": "GET", "path": path, "params": dict(params)})
    url = f"{base_url()}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"X-Api-Key": api_key() or "", "Accept": "application/json"}
    )
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        hint = " (check that the key is a hackathon key)" if exc.code == 401 else ""
        raise QlooError(f"Qloo {exc.code} on {path}{hint}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise QlooError(f"Qloo unreachable: {exc}") from exc


# ---- a small on-disk cache: entity and tag IDs barely change ---------------------


def _cache_path(source: str = "qloo") -> Path:
    # Demo answers live in their own file so they never mix with real ones.
    name = "qloo-demo-cache.json" if source == "demo" else "qloo-cache.json"
    return state_path().with_name(name)


def _cache_load(source: str = "qloo") -> dict:
    try:
        data = json.loads(_cache_path(source).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_save(cache: dict, source: str = "qloo") -> None:
    try:
        path = _cache_path(source)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2) + "\n")
        tmp.replace(path)
    except OSError:
        pass


def _cached(cache: dict, key: str, compute, trace=None):
    hit = cache.get(key)
    if isinstance(hit, dict) and time.time() - hit.get("at", 0) < CACHE_TTL_SECONDS:
        if trace is not None:
            trace.append({"cached": key.split(":x=")[0]})
        return hit.get("value")
    value = compute()
    cache[key] = {"value": value, "at": time.time()}
    return value


# ---- Qloo lookups ----------------------------------------------------------------------


def resolve_entity(
    name: str, entity_type: str, *, opener=urllib.request.urlopen, trace=None
) -> str | None:
    """Name -> Qloo entity ID, searched within one entity type."""
    data = _get(
        "/search",
        {"query": name, "types": entity_type, "take": "1"},
        opener=opener,
        trace=trace,
    )
    results = data.get("results") or []
    first = results[0] if results and isinstance(results[0], dict) else {}
    return first.get("entity_id") or None


def resolve_artist(name: str, *, opener=urllib.request.urlopen, trace=None) -> str | None:
    """Artist name -> Qloo entity ID."""
    return resolve_entity(name, SEED_TYPES["artists"], opener=opener, trace=trace)


def _tag_id(tag: dict) -> str | None:
    return tag.get("id") or tag.get("tag_id") or None


def resolve_genre_tag(genre: str, *, opener=urllib.request.urlopen, trace=None) -> str | None:
    """Genre word -> Qloo music-genre tag ID."""
    data = _get(
        "/v2/tags",
        {"filter.query": genre, "filter.tag.types": "urn:tag:genre:music", "take": "1"},
        opener=opener,
        trace=trace,
    )
    tags = (data.get("results") or {}).get("tags") or []
    if tags and isinstance(tags[0], dict) and _tag_id(tags[0]):
        return _tag_id(tags[0])
    # Some deployments don't filter by tag type; search broadly and keep a
    # music-genre tag if one comes back.
    data = _get("/v2/tags", {"filter.query": genre, "take": "10"}, opener=opener, trace=trace)
    for tag in (data.get("results") or {}).get("tags") or []:
        tid = _tag_id(tag) if isinstance(tag, dict) else None
        if tid and tid.startswith("urn:tag:genre:music"):
            return tid
    return None


def artist_picks(
    seed_ids: list[str],
    tag_id: str | None,
    *,
    exclude_ids: list[str] | None = None,
    take: int = 10,
    opener=urllib.request.urlopen,
    trace=None,
) -> list[dict]:
    """Artists Qloo predicts for this taste, steered toward a genre."""
    params = {
        "filter.type": "urn:entity:artist",
        "signal.interests.entities": ",".join(seed_ids),
        "take": str(take),
    }
    if tag_id:
        params["signal.interests.tags"] = tag_id
    exclude = [e for e in dict.fromkeys(list(seed_ids) + list(exclude_ids or []))]
    if exclude:
        params["filter.exclude.entities"] = ",".join(exclude)
    data = _get("/v2/insights", params, opener=opener, trace=trace)
    entities = (data.get("results") or {}).get("entities") or []
    picks = []
    for e in entities:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        affinity = (
            (e.get("query") or {}).get("affinity") if isinstance(e.get("query"), dict) else None
        )
        picks.append(
            {
                "name": str(e["name"]),
                "entity_id": e.get("entity_id"),
                "affinity": affinity if isinstance(affinity, (int, float)) else None,
            }
        )
    return picks


def artist_insights(
    seed_ids: list[str], tag_id: str | None, *, take: int = 10, opener=urllib.request.urlopen
) -> list[str]:
    """Names only, for callers that just need the artists."""
    return [p["name"] for p in artist_picks(seed_ids, tag_id, take=take, opener=opener)]


def _seed_lists(taste: list[str], extra: dict[str, list[str]] | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = [("artists", n) for n in taste[:MAX_SEEDS_PER_TYPE]]
    for kind, names in (extra or {}).items():
        if kind in SEED_TYPES and kind != "artists":
            pairs += [(kind, n) for n in names[:MAX_SEEDS_PER_TYPE]]
    return [(k, n.strip()) for k, n in pairs if n and n.strip()]


def recommend(
    vibe: str,
    taste: list[str],
    *,
    extra_taste: dict[str, list[str]] | None = None,
    exclude_ids: list[str] | None = None,
    opener=None,
) -> Recommendation:
    """Artists for this vibe and this listener. Raises QlooError if Qloo can't help.

    `taste` is a list of artist names; `extra_taste` adds films, shows, books
    or podcasts (keys from SEED_TYPES). `exclude_ids` keeps already-played
    artists out, so a session doesn't repeat itself.
    """
    source = "qloo"
    if opener is None:
        if demo_mode():
            opener, source = DemoQloo(), "demo"
        else:
            opener = urllib.request.urlopen
    elif isinstance(opener, DemoQloo):
        source = "demo"
    if source == "qloo" and not api_key():
        raise QlooError("QLOO_API_KEY is not set")
    seeds_wanted = _seed_lists(taste, extra_taste)
    if not seeds_wanted:
        raise QlooError("no taste artists configured")

    trace: list[dict] = []
    cache = _cache_load(source)
    try:
        seeds: list[str] = []
        seed_entities: list[dict] = []
        notes: list[str] = []
        for kind, name in seeds_wanted:
            etype = SEED_TYPES[kind]
            entity = _cached(
                cache,
                f"{etype}:{name.lower()}",
                lambda n=name, t=etype: resolve_entity(n, t, opener=opener, trace=trace),
                trace,
            )
            if entity:
                seeds.append(entity)
                seed_entities.append({"name": name, "kind": kind, "entity_id": entity})
            else:
                notes.append(f"Qloo doesn't know {name!r}")
        if not seeds:
            raise QlooError("none of your taste artists were found on Qloo")

        genre = VIBE_GENRES.get(vibe)
        tag_id = None
        if genre:
            try:
                tag_id = _cached(
                    cache,
                    f"tag:{genre}",
                    lambda: resolve_genre_tag(genre, opener=opener, trace=trace),
                    trace,
                )
            except QlooError as exc:
                notes.append(f"genre tag lookup failed ({exc}); using taste alone")

        excluded = sorted(set(exclude_ids or []))
        key = f"insights:{vibe}:{','.join(sorted(seeds))}:x={','.join(excluded)}"
        picks = _cached(
            cache,
            key,
            lambda: artist_picks(seeds, tag_id, exclude_ids=excluded, opener=opener, trace=trace),
            trace,
        )
    finally:
        _cache_save(cache, source)

    taste_lower = {n.lower() for _, n in seeds_wanted}
    fresh = [p for p in picks or [] if p["name"].lower() not in taste_lower]
    if not fresh:
        raise QlooError("Qloo returned no new artists")
    return Recommendation(
        artists=[p["name"] for p in fresh],
        seeds=[n for _, n in seeds_wanted if any(s["name"] == n for s in seed_entities)],
        genre=genre,
        tag_id=tag_id,
        notes=notes,
        picks=fresh,
        seed_entities=seed_entities,
        trace=trace,
        source=source,
    )


def station_queries(rec: Recommendation, limit: int = 3) -> list[str]:
    return [f"{artist} radio" for artist in rec.artists[:limit]]


# ---- demo mode -----------------------------------------------------------------------
#
# A tiny, hand-written stand-in for the three endpoints taskfm uses, so the
# whole flow can be shown without a key. These lists are illustrative picks
# written for this repo, not Qloo output, and every demo result says so.

_DEMO_GENRE_ARTISTS: dict[str, list[str]] = {
    "techno": ["Four Tet", "Floating Points", "Jon Hopkins", "Caribou", "Moderat", "Kiasmos"],
    "synthwave": ["The Midnight", "FM-84", "Gunship", "Kavinsky", "Timecop1983", "Com Truise"],
    "jazz": ["Kamasi Washington", "BadBadNotGood", "Nubya Garcia", "Yussef Dayes", "GoGo Penguin"],
    "indie pop": ["Phoenix", "Beach House", "Tame Impala", "Japanese Breakfast", "Alvvays"],
    "classical": ["Max Richter", "Olafur Arnalds", "Hania Rani", "Johann Johannsson"],
    "ambient": ["Brian Eno", "Stars of the Lid", "Hammock", "Helios", "Tim Hecker"],
    "electronic": ["Bonobo", "Tycho", "Rival Consoles", "Ulrich Schnauss", "Boards of Canada"],
}


class DemoQloo:
    """Answers /search, /v2/tags and /v2/insights from the sample table above."""

    def __call__(self, request, timeout):
        import io

        url = urllib.parse.urlparse(request.full_url)
        params = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/search":
            q = params.get("query", "").strip()
            slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
            body = {"results": [{"entity_id": f"demo-{slug}", "name": q}] if slug else []}
        elif url.path == "/v2/tags":
            q = params.get("filter.query", "").lower()
            slug = re.sub(r"[^a-z0-9]+", "_", q).strip("_")
            ok = q in _DEMO_GENRE_ARTISTS
            body = {"results": {"tags": [{"id": f"urn:tag:genre:music:{slug}"}] if ok else []}}
        elif url.path == "/v2/insights":
            tag = params.get("signal.interests.tags", "")
            genre = tag.rsplit(":", 1)[-1].replace("_", " ") if tag else "electronic"
            excluded = set(params.get("filter.exclude.entities", "").split(","))
            names = _DEMO_GENRE_ARTISTS.get(genre, _DEMO_GENRE_ARTISTS["electronic"])
            entities = []
            for n in names:
                eid = "demo-" + re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
                if eid not in excluded:
                    entities.append({"name": n, "entity_id": eid})
            body = {"results": {"entities": entities[: int(params.get("take", "10"))]}}
        else:
            raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
        return io.BytesIO(json.dumps(body).encode())
