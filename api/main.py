"""FastAPI service: classify articles, push articles into the Kafka pipeline,
stream live verdicts, and expose model metrics + pipeline health.

    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import config
from pipeline.model import META_FIELDS, predict
from pipeline.registry import load_latest

log = logging.getLogger("api")
STATIC = Path(__file__).parent / "static"


class Article(BaseModel):
    title: str | None = Field(default=None, max_length=1_000)
    text: str = Field(min_length=1, max_length=200_000)
    # Optional claim metadata (LIAR-style). Supplying any of these routes to the claim model.
    speaker: str | None = Field(default=None, max_length=200, examples=["barack-obama"])
    party: str | None = Field(default=None, max_length=100, examples=["democrat"])
    subject: str | None = Field(default=None, max_length=300, description="comma-separated topics",
                                examples=["economy,taxes"])
    context: str | None = Field(default=None, max_length=300, examples=["a campaign speech"])
    state: str | None = Field(default=None, max_length=100)

    def meta(self) -> dict:
        return {f: getattr(self, f) for f in META_FIELDS}


class Term(BaseModel):
    term: str
    weight: float
    direction: str


class Prediction(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    label: str
    label_id: int
    confidence: float
    probabilities: dict[str, float]
    route: str = Field(description="which sub-model scored it: 'article' or 'claim'")
    top_terms: list[Term]
    model: str | None
    model_version: str | None
    latency_ms: float


class State:
    """Process-wide mutable state guarded by a lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pipe = None
        self.metrics: dict = {}
        self.origin: str | None = None
        self.producer = None
        self.recent: deque[dict] = deque(maxlen=300)
        self.stream_connected = False

    def load_model(self) -> bool:
        pipe, metrics, origin = load_latest()
        if pipe is None:
            return False
        with self.lock:
            self.pipe, self.metrics, self.origin = pipe, metrics, origin
        log.info("model %s (%s) loaded from %s", metrics.get("best_model"), metrics.get("version"), origin)
        return True


state = State()


# --------------------------------------------------------------------------- background jobs

def _model_watcher() -> None:
    """Load the model at startup; keep retrying until one exists, then watch for new versions."""
    while True:
        try:
            current = state.metrics.get("version")
            pipe, metrics, origin = load_latest()
            if pipe is not None and metrics.get("version") != current:
                with state.lock:
                    state.pipe, state.metrics, state.origin = pipe, metrics, origin
                log.info("model %s (%s) loaded from %s", metrics.get("best_model"), metrics.get("version"), origin)
        except Exception as exc:  # noqa: BLE001
            log.warning("model watcher: %s", exc)
        time.sleep(30 if state.pipe is None else 120)


def _stream_follower() -> None:
    """Tail the predictions topic into an in-memory ring buffer for the live feed."""
    from pipeline.kafka_io import make_consumer
    while True:
        try:
            consumer = make_consumer(config.TOPIC_PREDICTIONS, group_id=None,
                                     auto_offset_reset="earliest", consumer_timeout_ms=-1)
            state.stream_connected = True
            for msg in consumer:
                state.recent.append(msg.value)
        except Exception as exc:  # noqa: BLE001
            state.stream_connected = False
            log.warning("stream follower: %s; retrying in 10s", exc)
            time.sleep(10)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_model_watcher, daemon=True, name="model-watcher").start()
    threading.Thread(target=_stream_follower, daemon=True, name="stream-follower").start()
    yield


app = FastAPI(
    title="Fake News Classification API",
    description="TF-IDF + Logistic Regression / Naive Bayes over Kafka-ingested, HDFS-stored news.",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- helpers

def _require_model():
    with state.lock:
        pipe, metrics = state.pipe, state.metrics
    if pipe is None:
        raise HTTPException(503, "No trained model available yet. Run the trainer first.")
    return pipe, metrics


def _classify(pipe, metrics, art: Article) -> dict:
    t0 = time.perf_counter()
    res = predict(pipe, art.title, art.text, art.meta())
    res.update(model=metrics.get("best_model"), model_version=metrics.get("version"),
               latency_ms=round((time.perf_counter() - t0) * 1000, 2))
    return res


def _tcp_ok(hostport: str, timeout: float = 1.5) -> bool:
    host, _, port = hostport.split(",")[0].rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _hdfs_ok() -> bool:
    try:
        from hdfs import InsecureClient
        InsecureClient(config.HDFS_URL, user=config.HDFS_USER, timeout=2).status("/")
        return True
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- routes

@app.post("/predict", response_model=Prediction, tags=["classify"])
def predict_one(article: Article):
    """Label one article as reliable / unreliable with a confidence score and the terms that drove it."""
    pipe, metrics = _require_model()
    return _classify(pipe, metrics, article)


@app.post("/predict/batch", response_model=list[Prediction], tags=["classify"])
def predict_batch(articles: list[Article]):
    if len(articles) > 500:
        raise HTTPException(413, "At most 500 articles per batch.")
    pipe, metrics = _require_model()
    return [_classify(pipe, metrics, a) for a in articles]


@app.post("/ingest", tags=["pipeline"])
def ingest(article: Article):
    """Publish an article to Kafka (`news-incoming`); the live scorer classifies it asynchronously."""
    from pipeline.kafka_io import make_producer
    try:
        if state.producer is None:
            state.producer = make_producer()
        rec = {
            "id": f"live-{uuid.uuid4().hex[:12]}",
            "source": "live",
            "title": article.title or "",
            "text": article.text,
            **{k: v for k, v in article.meta().items() if v},
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        state.producer.send(config.TOPIC_INCOMING, key=rec["id"], value=rec).get(timeout=10)
    except Exception as exc:  # noqa: BLE001
        state.producer = None
        raise HTTPException(503, f"Kafka unavailable: {exc}") from exc
    return {"status": "queued", "id": rec["id"], "topic": config.TOPIC_INCOMING}


@app.get("/stream/recent", tags=["pipeline"])
def stream_recent(limit: int = Query(50, ge=1, le=300)):
    """Most recent live verdicts from the `news-predictions` topic, newest first."""
    # The topic has several partitions, so arrival order isn't time order; sort by score time.
    items = sorted(state.recent, key=lambda i: i.get("scored_at") or "", reverse=True)[:limit]
    return {"connected": state.stream_connected, "count": len(items), "items": items}


@app.get("/model", tags=["model"])
def model_info():
    _, metrics = _require_model()
    return {**metrics, "loaded_from": state.origin}


@app.post("/model/reload", tags=["model"])
def model_reload():
    if not state.load_model():
        raise HTTPException(404, "No model found on HDFS or locally.")
    return {"status": "reloaded", "version": state.metrics.get("version"), "from": state.origin}


@app.get("/health", tags=["pipeline"])
def health():
    kafka = _tcp_ok(config.KAFKA_BOOTSTRAP)
    hdfs = _hdfs_ok()
    model = state.pipe is not None
    return {
        "status": "ok" if (kafka and hdfs and model) else "degraded",
        "kafka": kafka,
        "hdfs": hdfs,
        "model": model,
        "model_version": state.metrics.get("version"),
        "model_origin": state.origin,
        "stream_connected": state.stream_connected,
    }


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.middleware("http")
async def _revalidate_static(request, call_next):
    """Make browsers revalidate UI assets so a redeploy is picked up without a hard refresh."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=STATIC), name="static")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logging.getLogger("kafka").setLevel(logging.WARNING)
