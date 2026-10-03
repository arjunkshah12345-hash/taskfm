from taskfm.cli import _ago, extract_prompt


def test_extract_plain_text():
    assert extract_prompt("fix the flaky websocket bug") == "fix the flaky websocket bug"


def test_extract_hook_json():
    payload = '{"session_id":"abc","cwd":"/tmp","prompt":"review the payments diff"}'
    assert extract_prompt(payload) == "review the payments diff"


def test_extract_json_falls_back_to_other_keys():
    assert extract_prompt('{"message": "ship it"}') == "ship it"
    assert extract_prompt('{"text": "ship it"}') == "ship it"


def test_extract_json_without_known_key_keeps_raw_text():
    raw = '{"theme": "dark"}'
    assert extract_prompt(raw) == raw


def test_extract_empty_and_non_json():
    assert extract_prompt("   ") == ""
    assert extract_prompt("{not json") == "{not json"


def test_ago_formats():
    assert _ago(5) == "5s ago"
    assert _ago(90) == "1m ago"
    assert _ago(7200) == "2h ago"
