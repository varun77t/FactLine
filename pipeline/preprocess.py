"""Text cleaning shared by training, the API and the live scorer."""
import re

_URL = re.compile(r"https?://\S+|www\.\S+")
_HTML = re.compile(r"<[^>]+>")
_NON_ALNUM = re.compile(r"[^a-z0-9\s']")
_APOS = re.compile(r"(?<!\w)'|'(?!\w)")
_WS = re.compile(r"\s+")


def clean_text(text: str | None) -> str:
    """Lowercase, drop URLs/HTML/punctuation, collapse whitespace."""
    if not text:
        return ""
    t = str(text).lower()
    t = _URL.sub(" ", t)
    t = _HTML.sub(" ", t)
    t = _NON_ALNUM.sub(" ", t)
    t = _APOS.sub(" ", t)
    return _WS.sub(" ", t).strip()


def model_input(title: str | None, text: str | None) -> str:
    """The exact string the model sees: cleaned title + body."""
    return clean_text(f"{title or ''} {text or ''}")
