"""Real-time scoring: consume new articles from Kafka, classify them, publish the verdicts
to the predictions topic and archive them on HDFS.

    news-incoming --> [live_scorer] --> news-predictions
                                   +--> hdfs:/news/predictions/dt=.../part-*.jsonl
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import config
from pipeline.hdfs_io import get_client, write_jsonl
from pipeline.hdfs_sink import partition_path
from pipeline.kafka_io import ensure_topics, make_consumer, make_producer
from pipeline.model import META_FIELDS, predict
from pipeline.registry import load_latest

log = logging.getLogger("live-scorer")

ARCHIVE_EVERY = 50          # records
ARCHIVE_SECONDS = 10.0
MODEL_CHECK_SECONDS = 120.0


def wait_for_model():
    while True:
        pipe, metrics, origin = load_latest()
        if pipe is not None:
            log.info("loaded model %s (%s) from %s", metrics.get("best_model"), metrics.get("version"), origin)
            return pipe, metrics
        log.info("no trained model yet; retrying in 15s")
        time.sleep(15)


def main() -> None:
    ensure_topics([config.TOPIC_INCOMING, config.TOPIC_PREDICTIONS])
    pipe, metrics = wait_for_model()
    hdfs = get_client()
    consumer = make_consumer(config.TOPIC_INCOMING, group_id="live-scorer", auto_offset_reset="latest")
    producer = make_producer()
    log.info("scoring '%s' -> '%s'", config.TOPIC_INCOMING, config.TOPIC_PREDICTIONS)

    archive: list[dict] = []
    last_archive = last_model_check = time.time()
    try:
        while True:
            for records in consumer.poll(timeout_ms=1000).values():
                for r in records:
                    art = r.value
                    t0 = time.perf_counter()
                    res = predict(pipe, art.get("title"), art.get("text"), {f: art.get(f) for f in META_FIELDS})
                    out = {
                        "id": art.get("id"),
                        "title": art.get("title", ""),
                        "snippet": (art.get("text") or "")[:280],
                        "source": art.get("source", "live"),
                        "submitted_at": art.get("ingested_at"),
                        "scored_at": datetime.now(timezone.utc).isoformat(),
                        "model": metrics.get("best_model"),
                        "model_version": metrics.get("version"),
                        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                        **res,
                    }
                    producer.send(config.TOPIC_PREDICTIONS, key=out["id"], value=out)
                    archive.append(out)
                    log.info("%s -> %s (%.2f)", out["id"], out["label"], out["confidence"])

            now = time.time()
            if archive and (len(archive) >= ARCHIVE_EVERY or now - last_archive >= ARCHIVE_SECONDS):
                producer.flush()
                write_jsonl(hdfs, partition_path(config.HDFS_PRED_DIR), archive)
                archive, last_archive = [], now
            if now - last_model_check >= MODEL_CHECK_SECONDS:
                last_model_check = now
                new_pipe, new_metrics, origin = load_latest()
                if new_pipe is not None and new_metrics.get("version") != metrics.get("version"):
                    pipe, metrics = new_pipe, new_metrics
                    log.info("hot-reloaded model %s from %s", metrics.get("version"), origin)
    except KeyboardInterrupt:
        pass
    finally:
        if archive:
            write_jsonl(hdfs, partition_path(config.HDFS_PRED_DIR), archive)
        producer.close()
        consumer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("kafka").setLevel(logging.WARNING)
    main()
