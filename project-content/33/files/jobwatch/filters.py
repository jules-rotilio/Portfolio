"""Filtre par type de poste : C#/.NET, Python, DevOps (+ exclusions)."""
from __future__ import annotations

import re

from .models import Job
from .text import normalize

# Motifs appliqués sur du texte normalisé (minuscules, sans accents).
CATEGORIES = {
    "csharp": r"(?<![a-z0-9])c ?#|c sharp|csharp|(?<![a-z0-9])\.net\b|\bdotnet\b|\basp ?\.?net\b|\bblazor\b",
    "python": r"\bpython\b|\bdjango\b|\bfastapi\b|\bflask\b",
    "devops": r"\bdev ?ops\b|\bdevsecops\b|\bsre\b|site reliability|\bkubernetes\b|\bk8s\b|\bopenshift\b"
              r"|\bplatform engineer|\bingenieur (systeme|cloud|plateforme)s? .*(cloud|devops|kubernetes)",
}

# Intitulés génériques : on regarde alors la description pour trouver la techno.
GENERIC_TITLE = r"\bdevelop|\bdev\b|\banalyste|\bingenieur|\bengineer|\bprogramm|\bconcepteur|\bfull ?stack|\bback ?end|\blogiciel"

DEFAULT_EXCLUDE = [
    r"\bsenior\b", r"\blead\b", r"\bprincipal\b", r"\bhead of\b", r"\bdirect(eur|or)\b", r"\bmanager\b",
    r"\bstage\b", r"\bstagiaire\b", r"\binternship\b", r"\balternan", r"\bapprenti", r"\bprofesseur\b",
    r"\bformateur\b",
]


class JobFilter:
    def __init__(self, cfg: dict):
        wanted = cfg.get("categories", list(CATEGORIES))
        self.categories = {name: re.compile(CATEGORIES[name]) for name in wanted}
        for name, pattern in (cfg.get("extra_categories") or {}).items():
            self.categories[name] = re.compile(pattern)
        self.exclude = [re.compile(p) for p in cfg.get("exclude_title", DEFAULT_EXCLUDE)]
        self.exclude_desc = [re.compile(p) for p in cfg.get("exclude_description", [])]
        self.generic = re.compile(GENERIC_TITLE)
        self.trust_alerts = cfg.get("trust_email_alerts", True)
        self.locations = [normalize(x) for x in cfg.get("locations", [])]

    def match(self, job: Job) -> bool:
        title = normalize(job.title)
        desc = normalize(job.description)
        if any(p.search(title) for p in self.exclude):
            return False
        if any(p.search(desc) for p in self.exclude_desc):
            return False
        if self.locations and job.location and not job.from_alert:
            loc = normalize(job.location)
            if not any(l in loc for l in self.locations):
                return False

        cats = [n for n, p in self.categories.items() if p.search(title)]
        if not cats and self.generic.search(title) and desc:
            cats = [n for n, p in self.categories.items() if p.search(desc)]
        if not cats and job.from_alert and self.trust_alerts:
            # L'alerte du site est déjà filtrée sur tes critères : on garde, sans étiquette.
            cats = ["alerte"]
        job.categories = cats
        return bool(cats)
