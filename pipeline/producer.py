"""Read the raw datasets, normalize them and publish each article to Kafka.

    python -m pipeline.producer                 # everything, as fast as possible
    python -m pipeline.producer --rate 50       # throttle to ~50 msgs/sec (demo)
    python -m pipeline.producer --limit 500 --sources liar
"""
from __future__ import annotations

import argparse
import csv
import logging
import time
from pathlib import Path
from typing import Iterator

import pandas as pd

import config
from pipeline.kafka_io import ensure_topics, make_producer
from pipeline.schema import LIAR_COLUMNS, normalize_kaggle, normalize_liar

log = logging.getLogger("producer")


def iter_kaggle(raw_dir: Path) -> Iterator[dict]:
    path = raw_dir / "kaggle" / "train.csv"
    if not path.exists():
        log.warning("Kaggle file missing: %s (skipping)", path)
        return
    df = pd.read_csv(path)
    for row in df.to_dict(orient="records"):
        rec = normalize_kaggle(row)
        if rec:
            yield rec


def iter_liar(raw_dir: Path) -> Iterator[dict]:
    for split in ("train", "valid", "test"):
        path = raw_dir / "liar" / f"{split}.tsv"
        if not path.exists():
            log.warning("LIAR file missing: %s (skipping)", path)
            continue
        df = pd.read_csv(path, sep="\t", header=None, names=LIAR_COLUMNS,
                         quoting=csv.QUOTE_NONE, dtype=str, on_bad_lines="skip")
        for row in df.to_dict(orient="records"):
            rec = normalize_liar(row, split)
            if rec:
                yield rec


def interleave(*iters: Iterator[dict]) -> Iterator[dict]:
    """Round-robin the sources so a throttled demo stream shows both datasets."""
    active = list(iters)
    while active:
        for it in list(active):
            try:
                yield next(it)
            except StopIteration:
                active.remove(it)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default="kaggle,liar")
    ap.add_argument("--limit", type=int, default=0, help="max messages (0 = all)")
    ap.add_argument("--rate", type=float, default=0, help="messages/sec (0 = unthrottled)")
    ap.add_argument("--topic", default=config.TOPIC_ARTICLES)
    args = ap.parse_args()

    ensure_topics([args.topic])
    producer = make_producer()
    sources = {s.strip() for s in args.sources.split(",")}
    iters = []
    if "kaggle" in sources:
        iters.append(iter_kaggle(config.DATA_RAW))
    if "liar" in sources:
        iters.append(iter_liar(config.DATA_RAW))

    sent, counts, t0 = 0, {}, time.time()
    for rec in interleave(*iters):
        producer.send(args.topic, key=rec["id"], value=rec)
        sent += 1
        counts[rec["source"]] = counts.get(rec["source"], 0) + 1
        if sent % 2000 == 0:
            log.info("sent %d %s", sent, counts)
        if args.rate:
            time.sleep(1.0 / args.rate)
        if args.limit and sent >= args.limit:
            break
    producer.flush()
    producer.close()
    log.info("done: %d messages to '%s' in %.1fs %s", sent, args.topic, time.time() - t0, counts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    main()
