"""Envoi des offres sur Discord via un webhook (notifications push sur le téléphone)."""
from __future__ import annotations

import json
import logging
import time

from .http import HttpError, request
from .models import Job
from .text import shorten

log = logging.getLogger(__name__)

SOURCE_STYLE = {
    "linkedin": ("LinkedIn", 0x700070),
    "indeed": ("Indeed", 0x0000AA),
    "hellowork": ("HelloWork", 0xFF6B00),
    "francetravail": ("France Travail", 0xE3051B),
}
CATEGORY_LABEL = {"csharp": "C#/.NET", "python": "Python", "devops": "DevOps", "alerte": "Alerte"}


def build_embed(job: Job) -> dict:
    label, color = SOURCE_STYLE.get(job.source, (job.source, 0x5865F2))
    embed = {
        "title": shorten(job.title, 250),
        "url": job.url,
        "color": color,
        "footer": {"text": " · ".join([label] + [CATEGORY_LABEL.get(c, c) for c in job.categories])},
    }
    # Entreprise, lieu et contrat dans des champs séparés, seulement s'ils sont connus.
    fields = [{"name": name, "value": shorten(value, 1024), "inline": True}
              for name, value in (("Entreprise", job.company), ("Lieu", job.location), ("Contrat", job.contract))
              if value]
    if fields:
        embed["fields"] = fields
    if job.description:
        embed["description"] = shorten(job.description, 280)
    if job.published:
        embed["timestamp"] = job.published.isoformat()
    return embed


class DiscordNotifier:
    def __init__(self, webhook_url: str, username: str = "Veille emploi", mention: str = "",
                 dry_run: bool = False):
        self.url = webhook_url
        self.username = username
        self.mention = mention
        self.dry_run = dry_run

    def _post(self, payload: dict) -> None:
        if self.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for _ in range(5):
            try:
                request("POST", self.url, json_body=payload)
                return
            except HttpError as e:
                if e.status == 429:  # limite de débit Discord
                    try:
                        wait = float(json.loads(e.body).get("retry_after", 2))
                    except ValueError:
                        wait = 2
                    time.sleep(wait + 0.5)
                    continue
                raise

    def send_jobs(self, jobs: list[Job]) -> None:
        # Un message par offre, pour pouvoir classer ou supprimer chacune séparément.
        for job in jobs:
            # « Intitulé · Entreprise · Lieu » en texte : c'est ce qu'affiche la notification du téléphone.
            summary = " · ".join(x for x in (job.title, job.company, job.location) if x)
            self._post({"username": self.username, "content": shorten(f"{self.mention} {summary}".strip(), 1900),
                        "embeds": [build_embed(job)],
                        "allowed_mentions": {"parse": ["users", "roles", "everyone"]}})
            time.sleep(2)  # Discord limite un webhook à environ 30 messages par minute

    def send_text(self, text: str) -> None:
        self._post({"username": self.username, "content": shorten(text, 1900)})

    def send_test(self) -> None:
        """Message de test (--test-webhook) : vérifie le webhook, la mention et le rendu d'une offre."""
        sample = Job(source="francetravail", source_id="test", title="EXEMPLE — Développeur C# (H/F)",
                     url="https://candidat.francetravail.fr/offres/recherche", company="Entreprise fictive",
                     location="69 - Lyon", contract="CDI", description="Carte de test : aucune offre réelle.",
                     categories=["csharp"])
        content = f"{self.mention} 🧪 Test du webhook jobwatch : voici à quoi ressemblera une offre."
        self._post({"username": self.username, "content": content.strip(), "embeds": [build_embed(sample)],
                    "allowed_mentions": {"parse": ["users", "roles", "everyone"]}})
