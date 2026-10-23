"""Client HTTP minimal (bibliothèque standard uniquement)."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)
USER_AGENT = "jobwatch/1.0 (veille emploi personnelle)"


class HttpError(Exception):
    def __init__(self, status: int, body: str, headers=None):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body
        self.headers = headers or {}


def request(method: str, url: str, *, json_body=None, headers: dict | None = None,
            timeout: float = 30, retries: int = 2):
    """Renvoie (status, headers, texte). Réessaie sur erreur réseau et 5xx."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code >= 500 and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise HttpError(e.code, text, dict(e.headers)) from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                log.warning("Erreur réseau sur %s (%s), nouvel essai", url.split("?")[0], e)
                time.sleep(2 * (attempt + 1))
                continue
            raise
