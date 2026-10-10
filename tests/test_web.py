import json
import threading
import urllib.error
import urllib.request

import pytest

from taskfm import qloo, web


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    monkeypatch.delenv("QLOO_MODE", raising=False)
    web._hits.clear()
    srv = web.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_page_and_health(server):
    status, html = call(server, "/")
    assert status == 200 and b"taskfm" in html
    status, body = call(server, "/healthz")
    assert json.loads(body) == {"ok": True, "qloo": "demo", "version": json.loads(body)["version"]}


def test_session_compares_generic_and_taste_stations_without_repeats(server):
    taste = {"artists": ["Bonobo", "Khruangbin"], "movies": ["Blade Runner 2049"]}
    tasks = ["fix the flaky websocket bug", "track down the race condition", "ok"]
    status, body = call(server, "/api/session", {"taste": taste, "tasks": tasks})
    out = json.loads(body)
    assert status == 200 and out["mode"] == "demo"
    first, second, third = out["steps"]
    assert first["vibe"] == "debug"
    assert first["without_qloo"]["station"] == "deep techno focus"
    assert first["qloo"]["source"] == "demo"
    assert {b["kind"] for b in first["qloo"]["because"]} == {"artists", "movies"}
    # Same vibe twice in a session: the second task gets a different artist.
    assert second["vibe"] == "debug"
    assert second["qloo"]["artist"] != first["qloo"]["artist"]
    excl = [r for r in second["qloo"]["requests"] if r.get("path") == "/v2/insights"][0]
    assert "filter.exclude.entities" in excl["params"]
    assert third["vibe"] is None


def test_task_text_never_reaches_qloo(server):
    secret = "migrate the acme-internal-payroll schema"
    _, body = call(server, "/api/session", {"taste": {"artists": ["Bonobo"]}, "tasks": [secret]})
    reqs = json.loads(body)["steps"][0]["qloo"]["requests"]
    assert "acme" not in json.dumps(reqs)


def test_no_taste_still_gives_the_keyword_station(server):
    _, body = call(server, "/api/session", {"taste": {}, "tasks": ["deploy with docker"]})
    step = json.loads(body)["steps"][0]
    assert step["without_qloo"]["station"] == "synthwave"
    assert "error" in step["qloo"]


def test_hook_endpoint_reads_agent_payloads(server):
    status, body = call(
        server, "/api/hook?artists=Bonobo", {"prompt": "review the payments pull request"}
    )
    out = json.loads(body)
    assert status == 200 and out["action"] == "play" and out["vibe"] == "review"
    assert out["because_you_like"] == ["Bonobo"]
    _, body = call(server, "/api/hook", {"prompt": "thanks"})
    assert json.loads(body)["action"] == "skip"


def test_bad_input_and_rate_limit(server, monkeypatch):
    assert call(server, "/api/session", {"tasks": []})[0] == 400
    assert call(server, "/nope")[0] == 404
    monkeypatch.setattr(web, "RATE_LIMIT", 2)
    web._hits.clear()
    codes = [call(server, "/api/hook", {"prompt": "write docs"})[0] for _ in range(3)]
    assert codes == [200, 200, 429]


def test_limits_are_enforced():
    taste = web.clean_taste({"artists": [f"a{i}" for i in range(20)], "evil": ["x"]})
    assert list(taste) == ["artists"] and len(taste["artists"]) == qloo.MAX_SEEDS_PER_TYPE
    out = web.plan_session({}, [f"task {i}" for i in range(20)])
    assert len(out["steps"]) == web.MAX_TASKS


def test_live_mode_uses_the_key_and_reports_errors(server, monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "k")
    monkeypatch.setenv("QLOO_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    _, body = call(server, "/api/session", {"taste": {"artists": ["Bonobo"]}, "tasks": ["fix bug"]})
    out = json.loads(body)
    assert out["mode"] == "qloo"
    assert "unreachable" in out["steps"][0]["qloo"]["error"]
    assert out["steps"][0]["qloo"]["fallback"] == "deep techno focus"
