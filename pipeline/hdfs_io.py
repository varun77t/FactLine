"""Thin helpers around the WebHDFS client."""
from __future__ import annotations

import io
import json
import logging
import time
from typing import Iterable, Iterator

from hdfs import InsecureClient

import config

log = logging.getLogger(__name__)


def get_client(retries: int = 30, delay: float = 2.0) -> InsecureClient:
    """Connect to WebHDFS, waiting for the NameNode to leave safe mode / come up."""
    client = InsecureClient(config.HDFS_URL, user=config.HDFS_USER, timeout=30)
    for attempt in range(1, retries + 1):
        try:
            client.status("/")
            return client
        except Exception as exc:  # noqa: BLE001 - any connection failure means "not ready yet"
            log.info("HDFS not ready (%s/%s): %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError(f"HDFS at {config.HDFS_URL} is unreachable")


def write_jsonl(client: InsecureClient, path: str, records: Iterable[dict]) -> int:
    buf = io.StringIO()
    n = 0
    for r in records:
        buf.write(json.dumps(r, ensure_ascii=False))
        buf.write("\n")
        n += 1
    client.write(path, data=buf.getvalue().encode("utf-8"), overwrite=True)
    return n


def iter_jsonl_files(client: InsecureClient, root: str) -> Iterator[str]:
    if client.status(root, strict=False) is None:
        return
    for dirpath, _dirs, files in client.walk(root):
        for f in sorted(files):
            if f.endswith(".jsonl"):
                yield f"{dirpath.rstrip('/')}/{f}"


def read_jsonl_dir(client: InsecureClient, root: str) -> list[dict]:
    rows: list[dict] = []
    for path in iter_jsonl_files(client, root):
        # Split raw bytes on b"\n" only: a text-mode reader would also break lines on
        # U+2028 / U+0085, which appear unescaped inside article bodies.
        with client.read(path) as reader:
            for line in reader.read().split(b"\n"):
                line = line.strip()
                if line:
                    rows.append(json.loads(line.decode("utf-8")))
    return rows


def write_bytes(client: InsecureClient, path: str, data: bytes) -> None:
    client.write(path, data=data, overwrite=True)


def read_bytes(client: InsecureClient, path: str) -> bytes:
    with client.read(path) as reader:
        return reader.read()
