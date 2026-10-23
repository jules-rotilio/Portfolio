"""Point d'entrée : python -m jobwatch [--once] [--dry-run] [--config config.toml]"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
import tomllib
from datetime import datetime, timezone

from .filters import JobFilter
from .http import HttpError
from .notify import DiscordNotifier
from .sources.email_alerts import EmailAlertsSource
from .store import Store

log = logging.getLogger("jobwatch")


def load_env_file(path: str = ".env") -> None:
    """Charge un fichier .env simple (CLE=valeur) sans écraser l'environnement existant."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_sources(cfg: dict) -> list:
    sources = []
    env = os.environ
    em = cfg.get("email", {})
    if em.get("enabled"):
        if env.get("IMAP_USER") and env.get("IMAP_PASSWORD"):
            sources.append(EmailAlertsSource(em, env["IMAP_USER"], env["IMAP_PASSWORD"]))
        else:
            log.warning("Alertes e-mail activées mais IMAP_USER / IMAP_PASSWORD manquants")
    return sources


def run_once(cfg: dict, sources: list, store: Store, job_filter: JobFilter, notifier: DiscordNotifier) -> int:
    first_run = store.is_empty()
    collected, errors = [], []
    for src in sources:
        try:
            collected.extend(src.fetch())
        except Exception as e:  # une source en panne ne bloque pas les autres
            log.exception("Source %s en erreur", src.name)
            errors.append(f"{src.name} : {e}")

    new_jobs = []
    for job in collected:
        if store.is_known(job):
            continue
        if not job_filter.match(job):
            store.add(job, notified=False)  # mémorisé pour ne pas le réévaluer
            continue
        new_jobs.append(job)
        store.add(job, notified=True)

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    new_jobs.sort(key=lambda j: j.published or epoch, reverse=True)
    limit = int(cfg.get("general", {}).get("first_run_limit", 15))
    if first_run and len(new_jobs) > limit:
        log.info("Premier lancement : %d offres, envoi des %d plus récentes", len(new_jobs), limit)
        notifier.send_text(f"Veille emploi démarrée : {len(new_jobs)} offres correspondantes trouvées, "
                           f"voici les {limit} plus récentes. Ensuite, seules les nouveautés arriveront ici.")
        new_jobs = new_jobs[:limit]

    if new_jobs:
        notifier.send_jobs(new_jobs)
    # Avertissements des sources (ex. alerte e-mail expirée), envoyés une seule fois.
    for src in sources:
        for key, text in getattr(src, "notices", []):
            if not store.is_notice_known(key):
                notifier.send_text(text)
                store.add_notice(key)
    if errors and cfg.get("general", {}).get("notify_errors", True):
        notifier.send_text("⚠️ Sources en erreur :\n" + "\n".join(errors))
    log.info("%d offres collectées, %d nouvelles notifiées, %d en base",
             len(collected), len(new_jobs), store.count())
    return len(new_jobs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobwatch", description="Veille d'offres d'emploi vers Discord")
    ap.add_argument("--config", default=os.environ.get("JOBWATCH_CONFIG", "config.toml"))
    ap.add_argument("--once", action="store_true", help="un seul passage puis sortie (pour cron)")
    ap.add_argument("--dry-run", action="store_true", help="affiche les messages au lieu de les envoyer")
    ap.add_argument("--debug-email", metavar="SITE", help="affiche les liens du dernier e-mail d'alerte "
                    "(linkedin, indeed, hellowork, francetravail)")
    ap.add_argument("--test-webhook", action="store_true",
                    help="envoie un message de test sur Discord (mention + carte d'exemple) puis sort")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)

    if args.debug_email:
        em = cfg.get("email", {})
        EmailAlertsSource(em, os.environ["IMAP_USER"], os.environ["IMAP_PASSWORD"]).debug_latest(args.debug_email)
        return 0

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook and not args.dry_run:
        log.error("DISCORD_WEBHOOK_URL manquant")
        return 1
    dcfg = cfg.get("discord", {})
    notifier = DiscordNotifier(webhook, dcfg.get("username", "Veille emploi"), dcfg.get("mention", ""),
                               dry_run=args.dry_run)
    if args.test_webhook:
        try:
            notifier.send_test()
        except (HttpError, OSError) as e:
            log.error("Échec de l'envoi sur Discord : %s", e)
            return 1
        log.info("Message de test %s", "affiché (--dry-run)" if args.dry_run else "envoyé sur Discord")
        return 0
    store = Store(cfg.get("general", {}).get("db_path", "data/jobs.db"))
    job_filter = JobFilter(cfg.get("filters", {}))
    sources = build_sources(cfg)
    if not sources:
        log.error("Aucune source configurée : voir config.toml et .env")
        return 1

    if args.once:
        run_once(cfg, sources, store, job_filter, notifier)
        return 0

    interval = int(cfg.get("general", {}).get("interval_minutes", 30)) * 60
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not stop:
        started = time.monotonic()
        try:
            run_once(cfg, sources, store, job_filter, notifier)
        except Exception:
            log.exception("Passage en échec")
        while not stop and time.monotonic() - started < interval:
            time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
