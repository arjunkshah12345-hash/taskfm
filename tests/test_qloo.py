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
