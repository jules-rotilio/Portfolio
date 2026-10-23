"""Modèle de données commun à toutes les sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .text import normalize


@dataclass
class Job:
    source: str            # site de l'alerte : "linkedin", "indeed", "hellowork", "francetravail"
    source_id: str         # identifiant unique dans la source
    title: str
    url: str
    company: str = ""
    location: str = ""
    description: str = ""
    contract: str = ""
    published: datetime | None = None
    from_alert: bool = False   # True si l'offre vient d'une alerte e-mail (déjà filtrée par le site)
    categories: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Empreinte inter-sources : même intitulé + même entreprise = même offre."""
        if not self.company:
            return ""
        return f"{normalize(self.title)}|{normalize(self.company)}"
