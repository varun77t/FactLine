"""Central configuration. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Kafka
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
TOPIC_ARTICLES = os.getenv("TOPIC_ARTICLES", "news-articles")        # bulk dataset ingestion
TOPIC_INCOMING = os.getenv("TOPIC_INCOMING", "news-incoming")        # live articles to be scored
TOPIC_PREDICTIONS = os.getenv("TOPIC_PREDICTIONS", "news-predictions")

# HDFS (WebHDFS)
HDFS_URL = os.getenv("HDFS_URL", "http://localhost:9870")
HDFS_USER = os.getenv("HDFS_USER", "hadoop")
HDFS_RAW_DIR = os.getenv("HDFS_RAW_DIR", "/news/raw")
HDFS_MODEL_DIR = os.getenv("HDFS_MODEL_DIR", "/news/models")
HDFS_PRED_DIR = os.getenv("HDFS_PRED_DIR", "/news/predictions")

# Local paths
DATA_RAW = Path(os.getenv("DATA_RAW", ROOT / "data" / "raw"))
LOCAL_MODEL_DIR = Path(os.getenv("LOCAL_MODEL_DIR", ROOT / "models"))

# Sink batching
SINK_BATCH_SIZE = int(os.getenv("SINK_BATCH_SIZE", "2000"))
SINK_FLUSH_SECONDS = float(os.getenv("SINK_FLUSH_SECONDS", "15"))

LABELS = {0: "reliable", 1: "unreliable"}
