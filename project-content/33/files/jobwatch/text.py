"""Petits utilitaires texte."""
from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    """Minuscules, sans accents, espaces compactés. Garde # + . pour « c# », « .net »."""
    s = strip_accents(html.unescape(s or "")).lower()
    s = re.sub(r"\((h/f|f/h|h-f|f-h|m/f|f/m|h / f|f / h)\)|\b(h/f|f/h|h-f|f-h|m/f)\b", " ", s)
    s = re.sub(r"[^a-z0-9#+.\s/-]", " ", s)
    return _SPACES.sub(" ", s).strip()


def clean_html(s: str) -> str:
    return _SPACES.sub(" ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def shorten(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"
