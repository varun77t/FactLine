"""Consume articles from Kafka and land them on HDFS as JSON-lines partitions.

Files: /news/raw/dt=YYYY-MM-DD/part-<epoch>-<uuid>.jsonl
Offsets are committed only after a batch is safely written (at-least-once).

    python -m pipeline.hdfs_sink                     # run forever
    python -m pipeline.hdfs_sink --exit-when-idle 30 # stop after 30s with no messages
"""
from __future__ import annotations

import argparse
import logging
import time
import uuid
from datetime import datetime, timezone

import config
from pipeline.hdfs_io import get_client, write_jsonl
from pipeline.kafka_io import ensure_topics, make_consumer

log = logging.getLogger("hdfs-sink")


def partition_path(root: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{root}/dt={now:%Y-%m-%d}/part-{int(now.timestamp())}-{uuid.uuid4().hex[:8]}.jsonl"


def run(topic: str, root: str, group: str, batch_size: int, flush_s: float, idle_exit: float) -> None:
    ensure_topics([topic])
    hdfs = get_client()
    hdfs.makedirs(root)
    consumer = make_consumer(topic, group_id=group, enable_auto_commit=False,
                             max_poll_records=500)
    log.info("sinking '%s' -> hdfs:%s (batch=%d, flush=%ss)", topic, root, batch_size, flush_s)

    buf: list[dict] = []
    last_flush = last_msg = time.time()
    total = 0

    def flush() -> None:
        nonlocal buf, last_flush, total
        if buf:
            path = partition_path(root)
            n = write_jsonl(hdfs, path, buf)
            consumer.commit()
            total += n
            log.info("wrote %d records -> %s (total %d)", n, path, total)
        buf = []
        last_flush = time.time()

    try:
        while True:
            polled = consumer.poll(timeout_ms=1000)
            for records in polled.values():
                buf.extend(r.value for r in records)
                last_msg = time.time()
            if len(buf) >= batch_size or (buf and time.time() - last_flush >= flush_s):
                flush()
            if idle_exit and not buf and time.time() - last_msg >= idle_exit:
                log.info("idle for %ss, exiting (total %d)", idle_exit, total)
                break
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        consumer.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default=config.TOPIC_ARTICLES)
    ap.add_argument("--root", default=config.HDFS_RAW_DIR)
    ap.add_argument("--group", default="hdfs-sink")
    ap.add_argument("--batch-size", type=int, default=config.SINK_BATCH_SIZE)
    ap.add_argument("--flush-seconds", type=float, default=config.SINK_FLUSH_SECONDS)
    ap.add_argument("--exit-when-idle", type=float, default=0)
    a = ap.parse_args()
    run(a.topic, a.root, a.group, a.batch_size, a.flush_seconds, a.exit_when_idle)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("kafka").setLevel(logging.WARNING)
    main()
