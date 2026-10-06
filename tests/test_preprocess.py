from pipeline.preprocess import clean_text, model_input


def test_clean_text():
    raw = "BREAKING!! Visit https://x.com/a <b>now</b> — it's   'huge'"
    assert clean_text(raw) == "breaking visit now it's huge"


def test_clean_text_empty():
    assert clean_text(None) == ""
    assert clean_text(float("nan")) == "nan"  # NaN is filtered upstream in schema; documented behavior


def test_model_input_joins_title():
    assert model_input("Title", "Body text.") == "title body text"
    assert model_input(None, "x y") == "x y"
