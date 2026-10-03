from taskfm.config import Config, State


def _clean_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TASKFM_CONFIG", str(tmp_path / "missing.toml"))
    for key in ("TASKFM_DISABLE", "TASKFM_ENGINE", "TASKFM_FALLBACK"):
        monkeypatch.delenv(key, raising=False)


def test_defaults_when_config_is_absent(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    cfg = Config.load()
    assert cfg.engine == "auto"
    assert cfg.min_score == 1.0
    assert cfg.window_seconds == 600
    assert cfg.fallback == "none"
    assert cfg.disabled is False
    assert cfg.queries == {} and cfg.playlists == {} and cfg.keywords == {}
    assert cfg.warnings == []


def test_loads_toml_config(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    path = tmp_path / "config.toml"
    path.write_text(
        'engine = "connect"\n'
        "min_score = 2\n"
        "window_seconds = 60\n"
        'fallback = "focus"\n'
        "[playlists]\n"
        'debug = "spotify:playlist:abc"\n'
        "[queries]\n"
        'design = ["ambient jazz", "piano"]\n'
        'data = "chillhop"\n'
        "[keywords]\n"
        'Rust = "focus"\n'
    )
    monkeypatch.setenv("TASKFM_CONFIG", str(path))

    cfg = Config.load()
    assert cfg.engine == "connect"
    assert cfg.min_score == 2.0
    assert cfg.window_seconds == 60
    assert cfg.fallback == "focus"
    assert cfg.playlists == {"debug": "spotify:playlist:abc"}
    assert cfg.queries["design"] == ["ambient jazz", "piano"]
    assert cfg.queries["data"] == ["chillhop"]  # a bare string becomes a one-item list
    assert cfg.keywords == {"rust": "focus"}  # keys are normalised to lowercase
    assert cfg.warnings == []


def test_unreadable_config_is_a_warning_not_a_crash(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    path = tmp_path / "broken.toml"
    path.write_text("this is not = = toml")
    monkeypatch.setenv("TASKFM_CONFIG", str(path))

    cfg = Config.load()
    assert cfg.warnings and "could not read" in cfg.warnings[0]
    assert cfg.engine == "auto"  # defaults still apply


def test_env_overrides_beat_the_file(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('engine = "connect"\n')
    monkeypatch.setenv("TASKFM_CONFIG", str(path))
    monkeypatch.setenv("TASKFM_DISABLE", "1")
    monkeypatch.setenv("TASKFM_ENGINE", "applescript")
    monkeypatch.setenv("TASKFM_FALLBACK", "data")

    cfg = Config.load()
    assert cfg.disabled is True
    assert cfg.engine == "applescript"
    assert cfg.fallback == "data"


def test_state_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state = State(last_vibe="debug", last_uri="spotify:playlist:abc", last_at=123.0)
    state.cursor["debug"] = 3
    state.save()

    again = State.load()
    assert again.last_vibe == "debug"
    assert again.last_uri == "spotify:playlist:abc"
    assert again.last_at == 123.0
    assert again.cursor == {"debug": 3}


def test_missing_or_corrupt_state_reads_as_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "nowhere"))
    assert State.load().last_vibe == ""

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    (tmp_path / "taskfm").mkdir()
    (tmp_path / "taskfm" / "state.json").write_text("{not json")
    empty = State.load()
    assert empty.last_vibe == "" and empty.cursor == {}
