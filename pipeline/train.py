"""Train TF-IDF + Logistic Regression and TF-IDF + Naive Bayes on the articles stored in HDFS,
compare them, and publish the winner (plus metrics) back to HDFS.

    python -m pipeline.train                # read /news/raw from HDFS
    python -m pipeline.train --from-local   # read data/raw directly (no HDFS; dev/testing)
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

import config
from pipeline.model import (CLAIM_MAX_WORDS, RoutedModel, global_top_terms, make_classifiers,
                            make_vectorizer, prepare, route_for)

log = logging.getLogger("train")


def load_from_hdfs() -> pd.DataFrame:
    from pipeline.hdfs_io import get_client, read_jsonl_dir
    client = get_client()
    rows = read_jsonl_dir(client, config.HDFS_RAW_DIR)
    log.info("read %d records from hdfs:%s", len(rows), config.HDFS_RAW_DIR)
    return pd.DataFrame(rows)


def load_from_local() -> pd.DataFrame:
    from pipeline.producer import iter_kaggle, iter_liar
    rows = list(iter_kaggle(config.DATA_RAW)) + list(iter_liar(config.DATA_RAW))
    log.info("read %d records from %s", len(rows), config.DATA_RAW)
    return pd.DataFrame(rows)


def scores(y_true, y_pred, p_unrel) -> dict:
    out = {
        "n": int(len(y_true)),
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "roc_auc": roc_auc_score(y_true, p_unrel) if len(set(y_true)) > 1 else None,
        # rows = actual [reliable, unreliable], cols = predicted
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()}


ROUTE_OF_SOURCE = {"kaggle": "article", "liar": "claim"}
META_COLS = ["speaker", "party", "subject", "context", "state"]


def evaluate(model: RoutedModel, te: pd.DataFrame) -> dict:
    """Score the test set exactly as production would: each row is routed by route_for(),
    not by its known source, so routing mistakes count against the model."""
    p = np.empty(len(te))
    routes = np.empty(len(te), dtype=object)
    for route, pipe in model.pipes.items():
        m = te["route"].to_numpy() == route
        if m.any():
            p[m] = pipe.predict_proba(te.loc[m, f"input_{route}"])[:, list(pipe.classes_).index(1)]
        routes[m] = route
    y, src = te["label"].to_numpy(), te["source"].to_numpy()
    pred = (p >= 0.5).astype(int)
    res = {"overall": scores(y, pred, p), "by_source": {}}
    for s in sorted(set(src)):
        m = src == s
        res["by_source"][s] = scores(y[m], pred[m], p[m])
    expected = np.array([ROUTE_OF_SOURCE.get(s, "article") for s in src])
    res["routing_accuracy"] = round(float((routes == expected).mean()), 4)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-local", action="store_true")
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--no-upload", action="store_true", help="skip writing the model to HDFS")
    args = ap.parse_args()

    df = load_from_local() if args.from_local else load_from_hdfs()
    if df.empty:
        raise SystemExit("No training data found. Run the producer + hdfs_sink first.")
    # Later HDFS partitions win, so re-ingested records (e.g. with new metadata fields) replace old ones.
    df = df.drop_duplicates(subset="id", keep="last").reset_index(drop=True)
    for c in ["title", "text", *META_COLS]:
        df[c] = df[c].fillna("") if c in df else ""
    df["label"] = df["label"].astype(int)
    metas = df[META_COLS].to_dict("records")
    df["route"] = [route_for(t, x, m) for t, x, m in zip(df["title"], df["text"], metas)]
    df["input_article"] = [prepare(t, x) for t, x in zip(df["title"], df["text"])]
    df["input_claim"] = [prepare(t, x, m, "claim") for t, x, m in zip(df["title"], df["text"], metas)]
    df = df[df["input_article"].str.len() > 0].reset_index(drop=True)
    log.info("dataset: %d rows | by source %s | by label %s", len(df),
             df["source"].value_counts().to_dict(), df["label"].value_counts().to_dict())

    strat = df["source"] + "_" + df["label"].astype(str)
    tr, te = train_test_split(df, test_size=args.test_size, stratify=strat, random_state=42)

    # One vectorizer per route, fitted once and shared by LR and NB so the comparison is fair.
    vecs, X_tr, y_tr = {}, {}, {}
    for source, route in ROUTE_OF_SOURCE.items():
        part = tr[tr["source"] == source]
        if part.empty:
            continue
        t0 = time.time()
        vecs[route] = make_vectorizer(route)
        X_tr[route] = vecs[route].fit_transform(part[f"input_{route}"])
        y_tr[route] = part["label"].to_numpy()
        log.info("%s tf-idf (%s): %d rows, %d features, fit in %.1fs", route, source, len(part),
                 len(vecs[route].vocabulary_), time.time() - t0)

    results, models = {}, {}
    for name in make_classifiers():
        t1 = time.time()
        pipes = {}
        for route in vecs:
            clf = clone(make_classifiers(route)[name]).fit(X_tr[route], y_tr[route])
            pipes[route] = Pipeline([("tfidf", vecs[route]), ("clf", clf)])
        model = RoutedModel(pipes, name)
        res = evaluate(model, te)
        res["train_seconds"] = round(time.time() - t1, 2)
        results[name], models[name] = res, model
        o = res["overall"]
        log.info("%-20s acc=%.4f f1=%.4f macroF1=%.4f auc=%s | by source acc %s | routing %.4f", name,
                 o["accuracy"], o["f1"], o["macro_f1"], o["roc_auc"],
                 {s: r["accuracy"] for s, r in res["by_source"].items()}, res["routing_accuracy"])

    best = max(results, key=lambda n: results[n]["overall"]["macro_f1"])
    best_model = models[best]
    now = datetime.now(timezone.utc)
    version = now.strftime("%Y%m%dT%H%M%SZ")
    metrics = {
        "version": version,
        "trained_at": now.isoformat(),
        "best_model": best,
        "selection_metric": "macro_f1",
        "architecture": "routed",
        "routing_rule": f"claim model if claim metadata is given, or no headline and < {CLAIM_MAX_WORDS} words; "
                        "otherwise article model",
        "n_train": int(len(tr)),
        "n_test": int(len(te)),
        "n_features": int(sum(len(v.vocabulary_) for v in vecs.values())),
        "features_by_route": {r: int(len(v.vocabulary_)) for r, v in vecs.items()},
        "rows_by_source": {k: int(v) for k, v in df["source"].value_counts().items()},
        "rows_by_label": {config.LABELS[int(k)]: int(v) for k, v in df["label"].value_counts().items()},
        "liar_label_mapping": {"reliable": ["true", "mostly-true", "half-true"],
                               "unreliable": ["barely-true", "false", "pants-fire"]},
        "models": results,
        "top_terms": global_top_terms(best_model.pipes.get("article") or next(iter(best_model.pipes.values()))),
        "top_terms_by_route": {r: global_top_terms(p) for r, p in best_model.pipes.items()},
        "data_source": "local" if args.from_local else f"hdfs:{config.HDFS_RAW_DIR}",
    }
    log.info("best model: %s (version %s)", best, version)

    buf = io.BytesIO()
    joblib.dump(best_model, buf, compress=3)
    model_bytes = buf.getvalue()
    metrics_bytes = json.dumps(metrics, indent=2).encode("utf-8")

    config.LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (config.LOCAL_MODEL_DIR / "model.joblib").write_bytes(model_bytes)
    (config.LOCAL_MODEL_DIR / "metrics.json").write_bytes(metrics_bytes)
    log.info("saved local copy -> %s (%.1f MB)", config.LOCAL_MODEL_DIR, len(model_bytes) / 1e6)

    if not args.no_upload and not args.from_local:
        from pipeline.hdfs_io import get_client, write_bytes
        client = get_client()
        for d in (f"{config.HDFS_MODEL_DIR}/v{version}", f"{config.HDFS_MODEL_DIR}/latest"):
            write_bytes(client, f"{d}/model.joblib", model_bytes)
            write_bytes(client, f"{d}/metrics.json", metrics_bytes)
            log.info("uploaded -> hdfs:%s", d)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    main()
