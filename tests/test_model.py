from sklearn.pipeline import Pipeline

from pipeline.model import (RoutedModel, make_classifiers, make_vectorizer, meta_tokens, predict, prepare,
                            route_for)


def test_meta_tokens():
    meta = {"speaker": "Barack Obama", "party": "democrat", "subject": "economy,taxes", "context": ""}
    assert meta_tokens(meta) == "spk_barack_obama party_democrat subj_economy subj_taxes"
    assert meta_tokens(None) == ""


def test_route_for():
    assert route_for(None, "Says the governor cut school funding.") == "claim"
    assert route_for("Headline", "Says the governor cut school funding.") == "article"
    assert route_for(None, "word " * 200) == "article"
    assert route_for("Headline", "long " * 200, {"speaker": "x"}) == "claim"   # metadata forces claim model


def test_prepare_claim_appends_meta():
    out = prepare(None, "Taxes went up!", {"party": "republican"}, "claim")
    assert out == "taxes went up party_republican"
    assert prepare(None, "Taxes went up!", {"party": "republican"}) == "taxes went up"  # article ignores meta


def _pipe(route, docs, labels):
    vec = make_vectorizer(route).set_params(min_df=1, max_df=1.0)
    return Pipeline([("tfidf", vec), ("clf", make_classifiers(route)["logistic_regression"])]).fit(docs, labels)


def test_routed_model_uses_claim_metadata():
    claim_docs = [prepare(None, "tax rates rose", {"party": p}, "claim")
                  for p in ["democrat", "republican"] * 6]
    claim_y = [0, 1] * 6
    article_docs = ["officials said budget report", "shocking secret share now"] * 6
    model = RoutedModel({"article": _pipe("article", article_docs, [0, 1] * 6),
                         "claim": _pipe("claim", claim_docs, claim_y)}, "logistic_regression")

    dem = predict(model, None, "Tax rates rose.", {"party": "democrat"})
    rep = predict(model, None, "Tax rates rose.", {"party": "republican"})
    assert dem["route"] == rep["route"] == "claim"
    assert dem["label"] == "reliable" and rep["label"] == "unreliable"
    assert any(t["term"].startswith("party_") for t in rep["top_terms"])

    art = predict(model, "Breaking", "shocking secret, share now")
    assert art["route"] == "article" and art["label"] == "unreliable"
