import math

import pytest

from pipeline.schema import liar_binary_label, normalize_kaggle, normalize_liar


@pytest.mark.parametrize("raw,expected", [
    ("true", 0), ("mostly-true", 0), ("half-true", 0),
    ("barely-true", 1), ("false", 1), ("pants-fire", 1),
    (" FALSE ", 1), ("unknown", None), ("", None),
])
def test_liar_mapping(raw, expected):
    assert liar_binary_label(raw) == expected


def test_normalize_kaggle():
    rec = normalize_kaggle({"id": 7, "title": "Hello", "author": math.nan, "text": "Body", "label": 1})
    assert rec["id"] == "kaggle-7"
    assert rec["source"] == "kaggle"
    assert rec["label"] == 1
    assert rec["author"] == ""


def test_normalize_kaggle_drops_empty_text():
    assert normalize_kaggle({"id": 1, "title": "t", "text": math.nan, "label": 0}) is None
    assert normalize_kaggle({"id": 1, "title": "t", "text": "  ", "label": 0}) is None


def test_normalize_liar():
    rec = normalize_liar({"json_id": "123.json", "label": "pants-fire", "statement": "A claim.",
                          "speaker": "someone", "subject": "taxes"}, "valid")
    assert rec["id"] == "liar-valid-123.json"
    assert rec["label"] == 1 and rec["label_raw"] == "pants-fire"
    assert rec["text"] == "A claim."
