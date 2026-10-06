"""Normalize rows from the Kaggle Fake News and LIAR datasets into one article record.

Unified record:
    {id, source, title, text, author, speaker, party, subject, context, state, label, label_raw, ingested_at}
    label: 0 = reliable, 1 = unreliable
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

# LIAR has six truthfulness classes; binarize them.
LIAR_RELIABLE = {"true", "mostly-true", "half-true"}
LIAR_UNRELIABLE = {"barely-true", "false", "pants-fire"}

LIAR_COLUMNS = [
    "json_id", "label", "statement", "subject", "speaker", "job_title", "state",
    "party", "barely_true_counts", "false_counts", "half_true_counts",
    "mostly_true_counts", "pants_on_fire_counts", "context",
]


def liar_binary_label(raw: str) -> int | None:
    raw = (raw or "").strip().lower()
    if raw in LIAR_RELIABLE:
        return 0
    if raw in LIAR_UNRELIABLE:
        return 1
    return None


def _s(v) -> str:
    """Stringify, mapping NaN/None to empty string."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_kaggle(row: dict) -> dict | None:
    """Kaggle 'fake-news' train.csv: id, title, author, text, label (1 = unreliable)."""
    text = _s(row.get("text"))
    label = row.get("label")
    if not text or label is None or _s(label) == "":
        return None
    label = int(float(label))
    if label not in (0, 1):
        return None
    return {
        "id": f"kaggle-{_s(row.get('id'))}",
        "source": "kaggle",
        "title": _s(row.get("title")),
        "text": text,
        "author": _s(row.get("author")),
        "speaker": "",
        "party": "",
        "subject": "",
        "context": "",
        "state": "",
        "label": label,
        "label_raw": str(label),
        "ingested_at": _now(),
    }


def normalize_liar(row: dict, split: str = "train") -> dict | None:
    """LIAR tsv row (see LIAR_COLUMNS). The statement becomes the text."""
    text = _s(row.get("statement"))
    raw = _s(row.get("label")).lower()
    label = liar_binary_label(raw)
    if not text or label is None:
        return None
    return {
        "id": f"liar-{split}-{_s(row.get('json_id'))}",
        "source": "liar",
        "title": "",
        "text": text,
        "author": "",
        "speaker": _s(row.get("speaker")),
        "party": _s(row.get("party")),
        "subject": _s(row.get("subject")),
        "context": _s(row.get("context")),
        "state": _s(row.get("state")),
        "label": label,
        "label_raw": raw,
        "ingested_at": _now(),
    }
