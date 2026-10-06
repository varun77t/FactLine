"""Create Kafka topics and HDFS directories. Idempotent."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline.hdfs_io import get_client  # noqa: E402
from pipeline.kafka_io import ensure_topics  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s init %(message)s")
logging.getLogger("kafka").setLevel(logging.WARNING)

ensure_topics([config.TOPIC_ARTICLES, config.TOPIC_INCOMING, config.TOPIC_PREDICTIONS])
logging.info("kafka topics ready")

hdfs = get_client(retries=60)
for d in (config.HDFS_RAW_DIR, config.HDFS_MODEL_DIR, config.HDFS_PRED_DIR):
    hdfs.makedirs(d)
    logging.info("hdfs dir ready: %s", d)
