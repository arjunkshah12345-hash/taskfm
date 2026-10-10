import io
import json
import urllib.error
import urllib.parse

import pytest

from taskfm import qloo
from taskfm.config import Config

ARTISTS = {"bonobo": "A-BONOBO", "khruangbin": "A-KHRUANGBIN"}


class FakeQloo:
    """Serves /search, /v2/tags and /v2/insights; records every request."""

    def __init__(self, *, fail_insights=False, tags=True):
        self.calls = []
        self.fail_insights = fail_insights
        self.tags = tags

    def __call__(self, request, timeout):
        url = urllib.parse.urlparse(request.full_url)
        params = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((url.path, params, request.get_header("X-api-key")))
        if url.path == "/search":
            entity = ARTISTS.get(params["query"].lower())
            body = {"results": [{"entity_id": entity, "name": params["query"]}] if entity else []}
        elif url.path == "/v2/tags":
            body = {
                "results": {
                    "tags": [{"id": f"urn:tag:genre:music:{params['filter.query']}"}]
                    if self.tags
                    else []
                }
            }
        elif url.path == "/v2/insights":
            if self.fail_insights:
                raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)
            body = {
                "results": {
                    "entities": [{"name": "Bonobo"}, {"name": "Four Tet"}, {"name": "Caribou"}]
                }
            }
        else:
            raise AssertionError(url.path)
        return io.BytesIO(json.dumps(body).encode())


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("QLOO_API_KEY", "k")
    monkeypatch.delenv("QLOO_BASE_URL", raising=False)


def test_recommend_uses_taste_and_vibe_genre():
    fake = FakeQloo()
    rec = qloo.recommend("debug", ["Bonobo", "Khruangbin", "Nobody Knows"], opener=fake)

    assert rec.artists == ["Four Tet", "Caribou"]  # taste seeds are not echoed back
    assert rec.genre == "techno"
    assert rec.tag_id == "urn:tag:genre:music:techno"
    assert any("Nobody Knows" in note for note in rec.notes)
    insights = [p for path, p, _ in fake.calls if path == "/v2/insights"][0]
    assert insights["filter.type"] == "urn:entity:artist"
    assert insights["signal.interests.entities"] == "A-BONOBO,A-KHRUANGBIN"
    assert insights["signal.interests.tags"] == "urn:tag:genre:music:techno"
    assert all(key == "k" for _, _, key in fake.calls)
    assert qloo.station_queries(rec) == ["Four Tet radio", "Caribou radio"]


def test_second_call_is_served_from_cache():
    qloo.recommend("debug", ["Bonobo"], opener=FakeQloo())
    second = FakeQloo()
    qloo.recommend("debug", ["Bonobo"], opener=second)
    assert second.calls == []


def test_missing_tag_still_recommends_on_taste_alone():
    fake = FakeQloo(tags=False)
    rec = qloo.recommend("docs", ["Bonobo"], opener=fake)
    assert rec.tag_id is None
    insights = [p for path, p, _ in fake.calls if path == "/v2/insights"][0]
    assert "signal.interests.tags" not in insights


def test_failures_raise_qloo_error_for_the_fallback_path():
    with pytest.raises(qloo.QlooError):
        qloo.recommend("debug", ["Bonobo"], opener=FakeQloo(fail_insights=True))
    with pytest.raises(qloo.QlooError, match="none of your taste artists"):
        qloo.recommend("debug", ["Nobody Knows"], opener=FakeQloo())


def test_no_key_or_no_taste_means_no_qloo(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY")
    with pytest.raises(qloo.QlooError, match="QLOO_API_KEY"):
        qloo.recommend("debug", ["Bonobo"], opener=FakeQloo())


def test_taste_from_config_file_and_env(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[taste]\nartists = ["Bonobo", "Khruangbin"]\n')
    monkeypatch.setenv("TASKFM_CONFIG", str(cfg_file))
    assert Config.load().taste == ["Bonobo", "Khruangbin"]
    monkeypatch.setenv("TASKFM_TASTE", "Four Tet, Caribou")
    assert Config.load().taste == ["Four Tet", "Caribou"]


def test_cross_domain_seeds_and_exclusions_go_to_insights():
    fake = FakeQloo()
    ARTISTS["blade runner 2049"] = "M-BR2049"
    try:
        rec = qloo.recommend(
            "debug",
            ["Bonobo"],
            extra_taste={"movies": ["Blade Runner 2049"], "nonsense": ["x"]},
            exclude_ids=["A-PLAYED"],
            opener=fake,
        )
    finally:
        del ARTISTS["blade runner 2049"]
    searches = [p for path, p, _ in fake.calls if path == "/search"]
    assert [s["types"] for s in searches] == ["urn:entity:artist", "urn:entity:movie"]
    insights = [p for path, p, _ in fake.calls if path == "/v2/insights"][0]
    assert insights["signal.interests.entities"] == "A-BONOBO,M-BR2049"
    assert insights["filter.exclude.entities"] == "A-BONOBO,M-BR2049,A-PLAYED"
    assert [s["kind"] for s in rec.seed_entities] == ["artists", "movies"]
    assert all(
        "X-Api-Key" not in json.dumps(t) and "k" != t.get("params", {}).get("key")
        for t in rec.trace
    )


def test_demo_mode_runs_the_pipeline_without_a_key(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY")
    monkeypatch.setenv("QLOO_MODE", "demo")
    rec = qloo.recommend("ship", ["Bonobo"])
    assert rec.source == "demo"
    assert rec.genre == "synthwave" and rec.artists
    # Demo answers are cached separately from real ones.
    assert qloo._cache_path("demo").name != qloo._cache_path("qloo").name


def test_tag_lookup_falls_back_to_a_broad_search():
    class OnlyBroadTags(FakeQloo):
        def __call__(self, request, timeout):
            url = urllib.parse.urlparse(request.full_url)
            params = dict(urllib.parse.parse_qsl(url.query))
            if url.path == "/v2/tags":
                self.calls.append((url.path, params, None))
                tags = (
                    []
                    if "filter.tag.types" in params
                    else [
                        {"tag_id": "urn:tag:keyword:media:techno"},
                        {"tag_id": "urn:tag:genre:music:techno"},
                    ]
                )
                return io.BytesIO(json.dumps({"results": {"tags": tags}}).encode())
            return super().__call__(request, timeout)

    assert qloo.resolve_genre_tag("techno", opener=OnlyBroadTags()) == "urn:tag:genre:music:techno"


def test_extra_taste_from_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[taste]\nartists = ["Bonobo"]\nmovies = ["Arrival"]\ntv_shows = []\n')
    monkeypatch.setenv("TASKFM_CONFIG", str(cfg_file))
    cfg = Config.load()
    assert cfg.taste == ["Bonobo"] and cfg.taste_extra == {"movies": ["Arrival"]}
