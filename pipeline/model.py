"""Model construction, routing, prediction and per-prediction explanations.

The production model is a RoutedModel holding two TF-IDF pipelines:
  * "article": trained on full news articles (Kaggle Fake News)
  * "claim":   trained on short political claims (LIAR), with speaker/party/subject/venue
               metadata appended as extra tokens
Short, headline-less text (or text with claim metadata) goes to the claim model; everything
else goes to the article model. One shared vocabulary served both kinds of text poorly.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

import config
from pipeline.preprocess import model_input

# Very long articles add little signal but blow up the bigram vocabulary, so cap them.
MAX_CHARS = 10_000
# Headline-less text shorter than this is treated as a claim (LIAR statements are ~18 words;
# 99.96% are under 60).
CLAIM_MAX_WORDS = 60
META_FIELDS = {"speaker": "spk", "party": "party", "subject": "subj", "context": "ctx", "state": "st"}
_META_CLEAN = re.compile(r"[^a-z0-9]+")


def make_vectorizer(route: str = "article") -> TfidfVectorizer:
    return TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=100_000,
        sublinear_tf=True,
        min_df=2 if route == "article" else 1,   # claims are short; keep rare words and speaker tokens
        max_df=0.9,
        stop_words="english",
        dtype=np.float32,
    )


def make_classifiers(route: str = "article") -> dict:
    return {
        "logistic_regression": LogisticRegression(C=10.0 if route == "article" else 1.0, max_iter=3000,
                                                  class_weight="balanced", solver="liblinear"),
        "naive_bayes": MultinomialNB(alpha=0.1),
    }


def meta_tokens(meta: dict | None) -> str:
    """{'speaker': 'Barack Obama', 'subject': 'economy,taxes'} -> 'spk_barack_obama subj_economy subj_taxes'."""
    if not meta:
        return ""
    out = []
    for field, prefix in META_FIELDS.items():
        for part in str(meta.get(field) or "").lower().split(","):
            part = _META_CLEAN.sub("_", part).strip("_")
            if part:
                out.append(f"{prefix}_{part}")
    return " ".join(out)


def has_meta(meta: dict | None) -> bool:
    return bool(meta) and any(str(meta.get(f) or "").strip() for f in META_FIELDS)


def route_for(title: str | None, text: str | None, meta: dict | None = None) -> str:
    if has_meta(meta):
        return "claim"
    if not (title or "").strip() and len((text or "").split()) < CLAIM_MAX_WORDS:
        return "claim"
    return "article"


def prepare(title: str | None, text: str | None, meta: dict | None = None, route: str = "article") -> str:
    base = model_input(title, text)[:MAX_CHARS]
    if route == "claim":
        tokens = meta_tokens(meta)
        return f"{base} {tokens}".strip() if tokens else base
    return base


class RoutedModel:
    """Two fitted pipelines plus the routing rule. Pickled whole with joblib."""

    def __init__(self, pipes: dict[str, Pipeline], name: str):
        self.pipes = pipes
        self.name = name

    def route(self, title, text, meta=None) -> str:
        r = route_for(title, text, meta)
        return r if r in self.pipes else next(iter(self.pipes))

    def p_unreliable(self, title, text, meta=None) -> tuple[float, str, str]:
        r = self.route(title, text, meta)
        pipe = self.pipes[r]
        prepared = prepare(title, text, meta, r)
        proba = pipe.predict_proba([prepared])[0]
        return float(proba[list(pipe.classes_).index(1)]), r, prepared


def _term_weights(pipe: Pipeline) -> np.ndarray:
    """Per-feature log-odds direction: positive pushes toward 'unreliable' (class 1)."""
    clf = pipe.named_steps["clf"]
    if hasattr(clf, "coef_"):
        return clf.coef_[0]
    if hasattr(clf, "feature_log_prob_"):
        return clf.feature_log_prob_[1] - clf.feature_log_prob_[0]
    raise TypeError(f"unsupported classifier {type(clf).__name__}")


def explain(pipe: Pipeline, prepared_text: str, k: int = 8) -> list[dict]:
    vec: TfidfVectorizer = pipe.named_steps["tfidf"]
    X = vec.transform([prepared_text]).tocsr()
    if X.nnz == 0:
        return []
    weights = _term_weights(pipe)
    names = vec.get_feature_names_out()
    contrib = X.data * weights[X.indices]
    order = np.argsort(contrib)
    neg = [i for i in order[:k] if contrib[i] < 0]
    pos = [i for i in order[::-1][:k] if contrib[i] > 0]
    out = [{"term": str(names[X.indices[i]]), "weight": round(float(contrib[i]), 4),
            "direction": "unreliable"} for i in pos]
    out += [{"term": str(names[X.indices[i]]), "weight": round(float(contrib[i]), 4),
             "direction": "reliable"} for i in neg]
    return out


def predict(model, title: str | None, text: str | None, meta: dict | None = None, k: int = 8) -> dict:
    """Works with a RoutedModel or (older models / tests) a single Pipeline."""
    if isinstance(model, RoutedModel):
        p_unrel, route, prepared = model.p_unreliable(title, text, meta)
        pipe = model.pipes[route]
    else:
        pipe, route = model, "article"
        prepared = prepare(title, text)
        p_unrel = float(pipe.predict_proba([prepared])[0][list(pipe.classes_).index(1)])
    label = 1 if p_unrel >= 0.5 else 0
    return {
        "label": config.LABELS[label],
        "label_id": label,
        "confidence": round(p_unrel if label else 1 - p_unrel, 4),
        "probabilities": {"reliable": round(1 - p_unrel, 4), "unreliable": round(p_unrel, 4)},
        "route": route,
        "top_terms": explain(pipe, prepared, k),
    }


def global_top_terms(pipe: Pipeline, k: int = 20) -> dict:
    weights = _term_weights(pipe)
    names = pipe.named_steps["tfidf"].get_feature_names_out()
    order = np.argsort(weights)
    return {
        "unreliable": [{"term": str(names[i]), "weight": round(float(weights[i]), 4)} for i in order[::-1][:k]],
        "reliable": [{"term": str(names[i]), "weight": round(float(weights[i]), 4)} for i in order[:k]],
    }
