"""Load the latest trained model: HDFS first (source of truth), local copy as a fallback."""
from __future__ import annotations

import io
import json
import logging

import joblib

import config

log = logging.getLogger(__name__)


def load_latest(prefer_hdfs: bool = True):
    """Return (pipeline, metrics, origin) or (None, None, None) if no model exists yet."""
    if prefer_hdfs:
        try:
            from pipeline.hdfs_io import get_client, read_bytes
            client = get_client(retries=3, delay=1)
            base = f"{config.HDFS_MODEL_DIR}/latest"
            if client.status(f"{base}/model.joblib", strict=False):
                pipe = joblib.load(io.BytesIO(read_bytes(client, f"{base}/model.joblib")))
                metrics = json.loads(read_bytes(client, f"{base}/metrics.json"))
                return pipe, metrics, f"hdfs:{base}"
        except Exception as exc:  # noqa: BLE001
            log.warning("could not load model from HDFS: %s", exc)

    model_path = config.LOCAL_MODEL_DIR / "model.joblib"
    if model_path.exists():
        metrics_path = config.LOCAL_MODEL_DIR / "metrics.json"
        metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
        return joblib.load(model_path), metrics, f"local:{model_path}"
    return None, None, None
