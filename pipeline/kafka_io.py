"""Kafka producer/consumer factories with start-up retries."""
from __future__ import annotations

import json
import logging
import time

from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError

import config

log = logging.getLogger(__name__)


def _retry(factory, what: str, retries: int = 30, delay: float = 2.0):
    for attempt in range(1, retries + 1):
        try:
            return factory()
        except KafkaError as exc:  # NoBrokersAvailable etc.
            log.info("Kafka not ready for %s (%s/%s): %s", what, attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError(f"Kafka at {config.KAFKA_BOOTSTRAP} is unreachable")


def make_producer(**kw) -> KafkaProducer:
    return _retry(lambda: KafkaProducer(
        bootstrap_servers=config.KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        linger_ms=20,
        compression_type="gzip",
        max_request_size=5 * 1024 * 1024,
        **kw,
    ), "producer")


def make_consumer(*topics: str, group_id: str | None, **kw) -> KafkaConsumer:
    kw.setdefault("auto_offset_reset", "earliest")
    return _retry(lambda: KafkaConsumer(
        *topics,
        bootstrap_servers=config.KAFKA_BOOTSTRAP,
        group_id=group_id,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        **kw,
    ), f"consumer {topics}")


def ensure_topics(names: list[str], partitions: int = 3) -> None:
    admin = _retry(lambda: KafkaAdminClient(bootstrap_servers=config.KAFKA_BOOTSTRAP), "admin")
    existing = set(admin.list_topics())
    new = [NewTopic(n, num_partitions=partitions, replication_factor=1)
           for n in names if n not in existing]
    if new:
        try:
            admin.create_topics(new)
        except TopicAlreadyExistsError:
            pass
    admin.close()
