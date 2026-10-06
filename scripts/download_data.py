"""Fetch the raw datasets into data/raw/.

    python scripts/download_data.py                       # LIAR + Kaggle Fake News (~100 MB total)
    python scripts/download_data.py --kaggle-csv PATH     # use a train.csv / train.csv.zip you already have

LIAR (Wang, 2017) is public. The Kaggle "Fake News" competition (UTK Machine Learning Club,
2018) has been taken down from kaggle.com, so its train.csv (20,800 rows:
id, title, author, text, label) is fetched from a public Hugging Face mirror that
reproduces it exactly.
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
LIAR_URL = "https://www.cs.ucsb.edu/~william/data/liar_dataset.zip"
KAGGLE_MIRROR_URL = "https://huggingface.co/datasets/Reyansh4/Fake-News-Classification/resolve/main/train.csv"
KAGGLE_COLUMNS = ["id", "title", "author", "text", "label"]


def get_liar() -> None:
    dest = RAW / "liar"
    if all((dest / f"{s}.tsv").exists() for s in ("train", "valid", "test")):
        print(f"[liar] already present in {dest}")
        return
    dest.mkdir(parents=True, exist_ok=True)
    print(f"[liar] downloading {LIAR_URL}")
    with urllib.request.urlopen(LIAR_URL, timeout=60) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            base = Path(name).name
            if base in ("train.tsv", "valid.tsv", "test.tsv", "README"):
                (dest / base).write_bytes(z.read(name))
    print(f"[liar] extracted to {dest}")


def _extract_csv(src: Path, dest: Path) -> None:
    if src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            member = next(n for n in z.namelist() if n.endswith("train.csv"))
            dest.write_bytes(z.read(member))
    else:
        shutil.copyfile(src, dest)


def get_kaggle(manual_csv: str | None) -> bool:
    dest_dir = RAW / "kaggle"
    dest = dest_dir / "train.csv"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if manual_csv:
        _extract_csv(Path(manual_csv), dest)
        print(f"[kaggle] copied {manual_csv} -> {dest}")
        return True
    if dest.exists():
        print(f"[kaggle] already present: {dest}")
        return True
    print(f"[kaggle] downloading {KAGGLE_MIRROR_URL} (~99 MB)")
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(KAGGLE_MIRROR_URL, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        with open(tmp, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        if header != KAGGLE_COLUMNS:
            raise ValueError(f"unexpected columns {header}")
        tmp.replace(dest)
    except Exception as exc:  # noqa: BLE001
        print(f"[kaggle] download failed: {exc}")
        tmp.unlink(missing_ok=True)
        return False
    print(f"[kaggle] saved {dest}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kaggle-csv", help="path to a manually downloaded train.csv or train.csv.zip")
    ap.add_argument("--skip-kaggle", action="store_true")
    ap.add_argument("--skip-liar", action="store_true")
    args = ap.parse_args()

    if not args.skip_liar:
        get_liar()
    if not args.skip_kaggle and not get_kaggle(args.kaggle_csv):
        print(
            "\n[kaggle] Could not fetch the Kaggle Fake News dataset automatically.\n"
            f"  Download train.csv from {KAGGLE_MIRROR_URL}\n"
            "  then run: python scripts/download_data.py --kaggle-csv <path-to-file>\n"
            "The pipeline still runs on LIAR alone in the meantime.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
