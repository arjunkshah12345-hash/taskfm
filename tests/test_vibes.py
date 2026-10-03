from taskfm.vibes import BY_NAME, classify


def vibe_of(prompt: str) -> str | None:
    match = classify(prompt)
    return match.vibe.name if match.vibe else None


def test_debug_prompts_land_on_debug():
    assert vibe_of("fix the flaky websocket reconnect bug") == "debug"
    assert vibe_of("there's a traceback when opening the settings dialog") == "debug"
    assert vibe_of("investigate why the build hangs on CI") == "debug"


def test_focus_prompts_land_on_focus():
    assert vibe_of("implement a binary search tree from scratch") == "focus"
    assert vibe_of("refactor the auth middleware into smaller modules") == "focus"
    assert vibe_of("write a parser for the config schema") == "focus"


def test_design_prompts_land_on_design():
    assert vibe_of("redesign the landing page hero with a new color palette") == "design"
    assert vibe_of("add a dark mode theme and fix the css layout") == "design"
    assert vibe_of("animate the modal with a gradient background") == "design"


def test_ship_prompts_land_on_ship():
    assert vibe_of("deploy the service with docker and terraform") == "ship"
    assert vibe_of("set up github actions for the release pipeline") == "ship"
    assert vibe_of("the kubernetes rollout needs a rollback plan") == "ship"


def test_data_prompts_land_on_data():
    assert vibe_of("write a sql query for the analytics dashboard data") == "data"
    assert vibe_of("clean up this pandas dataframe and plot the csv") == "data"
    assert vibe_of("train the embeddings model on the dataset") == "data"


def test_docs_prompts_land_on_docs():
    assert vibe_of("update the readme and changelog") == "docs"
    assert vibe_of("write documentation for the public api") == "docs"
    assert vibe_of("proofread this blog article and fix the grammar") == "docs"


def test_review_prompts_land_on_review():
    assert vibe_of("review this pull request diff for the auth service") == "review"
    assert vibe_of("do a security audit of the payments module") == "review"
    assert vibe_of("help me understand the code in this directory") == "review"


def test_no_signal_leaves_music_alone():
    assert vibe_of("ok") is None
    assert vibe_of("") is None
    assert vibe_of("thanks") is None


def test_word_boundaries_do_not_bleed():
    # "css" must not match inside "scss"; "pr" must not match "improve".
    assert vibe_of("tune the scss variables") != "design"
    assert vibe_of("improve the function") != "review"


def test_plural_and_gerund_forms_match():
    assert vibe_of("the parser throws errors") == "debug"
    assert vibe_of("tune the css stylesheets") != "focus"
    assert vibe_of("refactoring the request pipeline") is not None


def test_nouns_outrank_generic_verbs():
    # "fix" pulls toward debug, but the object of the sentence is a readme.
    match = classify("update the readme with a fix note")
    assert match.vibe is not None
    assert match.vibe.name == "docs"
    assert match.score >= 2


def test_extra_keywords_from_config_win_by_count():
    match = classify("port the service to rust", extra_keywords={"rust": "focus"})
    assert match.vibe.name == "focus"


def test_fallback_only_applies_to_real_prompts():
    assert classify("add a header", fallback="focus").vibe.name == "design"
    assert classify("ok", fallback="focus").vibe is None
    assert classify("zzz qqq", fallback="focus").vibe is None
    assert classify("zzz qqq qqq", fallback="focus").vibe.name == "focus"


def test_every_vibe_has_search_queries():
    for name, vibe in BY_NAME.items():
        assert vibe.queries, name
        assert all(q.strip() for q in vibe.queries), name
        assert vibe.blurb, name
