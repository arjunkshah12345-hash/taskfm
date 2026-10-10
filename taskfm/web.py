"""The taskfm web app: a hosted, try-it-now version of the agent DJ.

    taskfm serve --host 0.0.0.0 --port 8787

Routes
    GET  /             the app (one static page)
    POST /api/session  {"taste": {...}, "tasks": [...]} -> a station per task
    POST /api/hook     an agent hook payload ({"prompt": ...}) -> one station
    GET  /healthz      liveness plus which Qloo mode is active

With QLOO_API_KEY set the server calls Qloo's hackathon API; without it, it
runs on taskfm's labelled demo table so the flow can still be explored. The
key stays on the server. Task text is classified here and never sent to Qloo;
Qloo only sees public cultural names (artists, films, shows) and a genre.

Standard library only, like the rest of taskfm.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from taskfm import __version__, qloo
from taskfm.vibes import BY_NAME, classify

MAX_TASKS = 8
MAX_TASK_CHARS = 500
MAX_NAME_CHARS = 80
MAX_BODY_BYTES = 64_000
RATE_LIMIT = int(os.environ.get("TASKFM_RATE_LIMIT", "30"))  # requests per minute per IP

_lock = threading.Lock()  # the Qloo cache is one file; one writer at a time
_hits: dict[str, deque] = defaultdict(deque)

SAMPLE_TASKS = [
    "Track down the race condition in the job queue that makes the flaky test fail",
    "Write the README section for the new plugin API",
    "Deploy the billing service with the new Docker image and Terraform change",
    "Explore last month's signup data in pandas and chart the funnel",
    "Review the payments pull request before merge",
]


def mode() -> str:
    return "qloo" if qloo.api_key() and not qloo.demo_mode() else "demo"


def spotify_search_url(text: str) -> str:
    return "https://open.spotify.com/search/" + urllib.parse.quote(text)


def _clean_names(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        s = str(v).strip()[:MAX_NAME_CHARS]
        if s and s.lower() not in {o.lower() for o in out}:
            out.append(s)
    return out[: qloo.MAX_SEEDS_PER_TYPE]


def clean_taste(raw) -> dict[str, list[str]]:
    raw = raw if isinstance(raw, dict) else {}
    return {k: names for k in qloo.SEED_TYPES if (names := _clean_names(raw.get(k)))}


def _redact(trace: list[dict]) -> list[dict]:
    # Requests never carry the key (it's a header), but keep this explicit.
    out = []
    for entry in trace:
        if "params" in entry:
            params = {k: v for k, v in entry["params"].items() if "key" not in k.lower()}
            out.append({**entry, "params": params})
        else:
            out.append(entry)
    return out


def station_for(task: str, taste: dict[str, list[str]], played: list[str]) -> dict:
    """Classify one task and pick a station, with and without Qloo."""
    match = classify(task, fallback="focus")
    if match.vibe is None:
        return {"task": task, "vibe": None, "reason": match.reason}
    vibe = match.vibe
    step = {
        "task": task,
        "vibe": vibe.name,
        "blurb": vibe.blurb,
        "score": match.score,
        "matched": [k for k, _ in match.matches][:6],
        "without_qloo": {
            "station": vibe.queries[0],
            "spotify_url": spotify_search_url(vibe.queries[0]),
            "note": "the same search for everyone in this vibe",
        },
    }
    if not taste:
        step["qloo"] = {"error": "add a few artists, films or shows you like"}
        return step
    opener = qloo.DemoQloo() if mode() == "demo" else None
    try:
        with _lock:
            rec = qloo.recommend(
                vibe.name,
                taste.get("artists", []),
                extra_taste={k: v for k, v in taste.items() if k != "artists"},
                exclude_ids=played,
                opener=opener,
            )
    except qloo.QlooError as exc:
        step["qloo"] = {"error": str(exc), "fallback": vibe.queries[0]}
        return step
    now = rec.picks[0]
    if now.get("entity_id"):
        played.append(now["entity_id"])
    step["qloo"] = {
        "source": rec.source,
        "station": f"{now['name']} radio",
        "spotify_url": spotify_search_url(f"{now['name']} radio"),
        "artist": now["name"],
        "affinity": now.get("affinity"),
        "also": [
            {"name": p["name"], "spotify_url": spotify_search_url(p["name"])}
            for p in rec.picks[1:6]
        ],
        "genre": rec.genre,
        "tag_id": rec.tag_id,
        "because": [{"name": s["name"], "kind": s["kind"]} for s in rec.seed_entities],
        "notes": rec.notes,
        "requests": _redact(rec.trace),
    }
    return step


def plan_session(taste_raw, tasks_raw) -> dict:
    taste = clean_taste(taste_raw)
    tasks = [str(t).strip()[:MAX_TASK_CHARS] for t in (tasks_raw or []) if str(t).strip()]
    tasks = tasks[:MAX_TASKS]
    played: list[str] = []
    steps = [station_for(t, taste, played) for t in tasks]
    return {"mode": mode(), "taste": taste, "steps": steps}


def hook(payload: dict, taste_raw) -> dict:
    """One agent prompt in, one station out: the hosted version of `taskfm start`."""
    from taskfm.cli import extract_prompt

    prompt = extract_prompt(json.dumps(payload)) if isinstance(payload, dict) else ""
    match = classify(prompt)
    if match.vibe is None:
        return {"action": "skip", "reason": match.reason}
    step = station_for(prompt, clean_taste(taste_raw), [])
    q = step.get("qloo") or {}
    if "station" in q:
        return {
            "action": "play",
            "vibe": step["vibe"],
            "station": q["station"],
            "spotify_url": q["spotify_url"],
            "because_you_like": [b["name"] for b in q["because"]],
            "genre": q["genre"],
            "source": q["source"],
        }
    w = step["without_qloo"]
    return {
        "action": "play",
        "vibe": step["vibe"],
        "station": w["station"],
        "spotify_url": w["spotify_url"],
        "source": "keywords",
        "note": q.get("error"),
    }


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return False
    q.append(now)
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = f"taskfm/{__version__}"

    def log_message(self, fmt, *args):  # quiet by default; set TASKFM_HTTP_LOG=1 to see requests
        if os.environ.get("TASKFM_HTTP_LOG"):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or self.client_address[0]

    def do_GET(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = resources.files("taskfm").joinpath("static/index.html").read_bytes()
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/healthz":
            return self._json(200, {"ok": True, "qloo": mode(), "version": __version__})
        if path == "/api/meta":
            return self._json(
                200,
                {
                    "qloo": mode(),
                    "samples": SAMPLE_TASKS,
                    "vibes": {
                        n: {"blurb": v.blurb, "genre": qloo.VIBE_GENRES.get(n)}
                        for n, v in BY_NAME.items()
                    },
                },
            )
        self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        if url.path not in ("/api/session", "/api/hook"):
            return self._json(404, {"error": "not found"})
        if not _rate_ok(self._ip()):
            return self._json(429, {"error": "slow down: too many requests this minute"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return self._json(413, {"error": "request too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "body must be JSON"})
        if not isinstance(body, dict):
            return self._json(400, {"error": "body must be a JSON object"})
        if url.path == "/api/session":
            if not body.get("tasks"):
                return self._json(400, {"error": "add at least one task"})
            return self._json(200, plan_session(body.get("taste"), body.get("tasks")))
        query = dict(urllib.parse.parse_qsl(url.query))
        return self._json(200, hook(body, {k: query.get(k, "") for k in qloo.SEED_TYPES}))


def make_server(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = make_server(host, port)
    print(f"taskfm web on http://{host}:{server.server_port}  (Qloo: {mode()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
