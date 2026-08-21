import pytest

import filter as filter_mod
from filter import _parse_json, filter_relevant


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeUsage:
    def __init__(self, completion_tokens=42):
        self.completion_tokens = completion_tokens


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]
        self.usage = FakeUsage()


class FakeCompletions:
    def __init__(self, response_fn):
        self._response_fn = response_fn

    def create(self, **kwargs):
        return self._response_fn(kwargs)


class FakeChat:
    def __init__(self, response_fn):
        self.completions = FakeCompletions(response_fn)


class FakeGroqClient:
    def __init__(self, response_fn):
        self.chat = FakeChat(response_fn)


def make_listing(lid):
    return {
        "id": lid,
        "title": f"Item {lid}",
        "description": "Eine Beschreibung",
        "location": "Thun",
        "postcode": "3600",
    }


def test_filter_relevant_empty_input_returns_empty():
    assert filter_relevant([], {"groq_api_key": "x"}) == []


def test_filter_relevant_missing_api_key_raises():
    with pytest.raises(RuntimeError, match="groq_api_key"):
        filter_relevant([make_listing("1")], {})


def test_filter_relevant_keeps_only_scores_above_threshold(monkeypatch):
    def response_fn(kwargs):
        return FakeResponse('[{"id": "1", "score": 9, "reason": "passt"}, '
                             '{"id": "2", "score": 2, "reason": "nicht relevant"}]')

    monkeypatch.setattr(filter_mod, "Groq", lambda api_key: FakeGroqClient(response_fn))

    listings = [make_listing("1"), make_listing("2")]
    result = filter_relevant(listings, {"groq_api_key": "x", "min_relevance_score": 6})

    assert [l["id"] for l in result] == ["1"]
    assert result[0]["score"] == 9
    assert result[0]["reason"] == "passt"


def test_filter_relevant_batches_and_skips_sleep_before_first_batch(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(filter_mod.time, "sleep", lambda s: sleep_calls.append(s))

    def response_fn(kwargs):
        import re
        ids = re.findall(r"ID: (\S+)", kwargs["messages"][0]["content"])
        items = [f'{{"id": "{i}", "score": 8, "reason": "ok"}}' for i in ids]
        return FakeResponse("[" + ",".join(items) + "]")

    monkeypatch.setattr(filter_mod, "Groq", lambda api_key: FakeGroqClient(response_fn))

    listings = [make_listing(str(i)) for i in range(15)]  # > BATCH_SIZE (12) -> 2 batches
    result = filter_relevant(listings, {"groq_api_key": "x", "min_relevance_score": 6})

    assert len(result) == 15
    assert sleep_calls == [25]  # only once, between the two batches


def test_parse_json_valid_array():
    assert _parse_json('noise [{"id": "1", "score": 5}] more noise') == [{"id": "1", "score": 5}]


def test_parse_json_no_array_returns_empty():
    assert _parse_json("kein JSON hier") == []


def test_parse_json_malformed_array_returns_empty():
    assert _parse_json("[{not valid json}]") == []
