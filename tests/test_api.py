import pytest
from fastapi.testclient import TestClient
from sklearn.pipeline import Pipeline

from api import main
from pipeline.model import make_classifiers, make_vectorizer, prepare

RELIABLE = [
    "the council voted on the budget after a public hearing officials said",
    "researchers published a study in the journal reporting modest results",
    "the senate committee approved the bill on tuesday according to records",
    "officials said the department would release the report next week",
] * 3
UNRELIABLE = [
    "shocking secret they dont want you to know share before deleted",
    "globalist elites hide the truth wake up patriots share now",
    "bombshell leaked proof the deep state is lying to you share",
    "miracle cure big pharma is terrified share this before censored",
] * 3


@pytest.fixture(scope="module")
def client():
    X = [prepare(None, t) for t in RELIABLE + UNRELIABLE]
    y = [0] * len(RELIABLE) + [1] * len(UNRELIABLE)
    vec = make_vectorizer().set_params(min_df=1, max_df=1.0)
    pipe = Pipeline([("tfidf", vec), ("clf", make_classifiers()["logistic_regression"])]).fit(X, y)
    main.state.pipe = pipe
    main.state.metrics = {"best_model": "logistic_regression", "version": "test"}
    return TestClient(main.app)  # no context manager -> startup background threads don't run


def test_predict_unreliable(client):
    r = client.post("/predict", json={"title": "SHOCKING", "text": "Share this secret before it is deleted, patriots!"})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "unreliable"
    assert 0.5 <= body["confidence"] <= 1
    assert abs(sum(body["probabilities"].values()) - 1) < 1e-3
    assert any(t["direction"] == "unreliable" for t in body["top_terms"])


def test_predict_reliable(client):
    r = client.post("/predict", json={"text": "Officials said the council approved the budget report."})
    assert r.json()["label"] == "reliable"


def test_batch(client):
    r = client.post("/predict/batch", json=[{"text": "officials said"}, {"text": "share the secret"}])
    assert [x["label"] for x in r.json()] == ["reliable", "unreliable"]


def test_validation(client):
    assert client.post("/predict", json={"text": ""}).status_code == 422


def test_no_model_returns_503(client):
    saved = main.state.pipe
    main.state.pipe = None
    try:
        assert client.post("/predict", json={"text": "x"}).status_code == 503
    finally:
        main.state.pipe = saved


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Factline" in r.text
