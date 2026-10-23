"""Lecture des alertes e-mail LinkedIn, Indeed, HelloWork et France Travail via IMAP.

Principe : tu crées une alerte sur chaque site (mots-clés + lieu). Les e-mails
arrivent dans ta boîte ; ce module les lit (sans les modifier) et extrait les
liens d'offres. Aucune page de ces sites n'est aspirée.
"""
from __future__ import annotations

import base64
import email
import imaplib
import logging
import re
import urllib.parse
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from html.parser import HTMLParser

from ..models import Job
from ..text import clean_html

log = logging.getLogger(__name__)

# Motifs de liens d'offres (cherchés dans l'URL décodée, redirections de suivi comprises).
# « after » : lignes de texte qui suivent le lien de l'intitulé (entreprise, lieu, contrat).
SITES = {
    "linkedin": {
        "pattern": re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*-)?(\d{6,})"),
        "url": "https://www.linkedin.com/jobs/view/{id}/",
        "after": re.compile(r"(?P<company>[^\n]+?) · (?P<location>[^\n]+)"),  # « Cegid · Lyon (Hybride) »
    },
    "indeed": {
        "pattern": re.compile(r"[?&/]jk=([0-9a-f]{16})"),
        "url": "https://fr.indeed.com/viewjob?jk={id}",
        "after": re.compile(r"(?P<company>[^\n]+)\n(?P<location>[^\n]+)"),  # « AXOPEN », « Lyon (69) »
    },
    "hellowork": {
        "pattern": re.compile(r"hellowork\.com/fr-fr/emplois/(\d+)\.html"),
        "url": "https://www.hellowork.com/fr-fr/emplois/{id}.html",
        # « Recrulab », [« Super recruteur »], « Vénissieux - 69 », « CDI »
        "after": re.compile(r"(?P<company>[^\n]+)\n(?:Super recruteur\n)?(?P<location>[^\n]+)\n(?P<contract>[^\n]+)"),
    },
    "francetravail": {
        "pattern": re.compile(r"candidat\.francetravail\.fr/offres/recherche/detail/(\w+)"),
        "url": "https://candidat.francetravail.fr/offres/recherche/detail/{id}",
        # 2e ligne du lien : « Entreprise - 69 - Lyon » ; l'entreprise peut manquer
        # et le lieu n'être qu'une région (« Île-de-France »).
        "details": re.compile(r"(?:(?P<company>(?!(?:\d{2,3}|2[AB])\s+-\s).+?)\s+-\s+)?"
                              r"(?P<location>(?:\d{2,3}|2[AB])\s+-\s+.+|(?:(?!\s-\s).)+)"),
        # France Travail supprime les alertes arrivées à échéance : on prévient pour les recréer.
        "expired": re.compile(r"alerte emploi\s*[\"«“]\s*(.+?)\s*[\"»”]\s*est\s+arrivée\s+à\s+échéance"),
        "expired_message": "⏰ Ton alerte France Travail « {name} » a expiré et a été supprimée : "
                           "recrée-la sur https://candidat.francetravail.fr/offres/recherche",
    },
}

# Textes de lien qui ne sont pas des intitulés de poste.
_NOISE = re.compile(
    r"^(voir|postuler|candidature|see|view|apply|en savoir|découvrir|decouvrir|plus d|"
    r"offre|logo|image|nouveau|new|\d+\s)", re.I)


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts: list[str] = []  # tous les textes du document, dans l'ordre
        self.anchors: list[tuple[str, str, int, int]] = []  # (href, texte, début, fin) ; début/fin indexent texts
        self._href = None
        self._start = 0
        self._lines: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        # Les <img> (logos) sont ignorés : seul le texte compte.
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._start = len(self.texts)
            self._lines = [[]]
        elif tag == "br" and self._href is not None:
            self._lines.append([])  # France Travail : « intitulé<br>entreprise - lieu » dans le même lien

    def handle_data(self, data):
        if data.strip():
            self.texts.append(" ".join(data.split()))
        if self._href is not None:
            self._lines[-1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            lines = (" ".join("".join(parts).split()) for parts in self._lines)
            text = "\n".join(line for line in lines if line)
            self.anchors.append((self._href, text, self._start, len(self.texts)))
            self._href = None


_B64_SEGMENT = re.compile(r"/([A-Za-z0-9_-]{16,}={0,2})(?=[/?#]|$)")


def _unwrap(url: str) -> str:
    """Décode plusieurs fois pour révéler l'URL cible cachée dans un lien de suivi."""
    prev = None
    for _ in range(4):
        if url == prev:
            break
        prev, url = url, urllib.parse.unquote(url)
    # HelloWork cache l'URL cible encodée en base64 dans un segment du chemin.
    for seg in _B64_SEGMENT.findall(url):
        try:
            decoded = base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)).decode("utf-8")
        except ValueError:
            continue
        if "http" in decoded:
            url += " " + decoded
    return url.replace("&amp;", "&")


def extract_jobs(html: str, site: str) -> list[Job]:
    """Extrait les offres d'un e-mail d'alerte HTML."""
    spec = SITES[site]
    parser = _AnchorParser()
    parser.feed(html)
    found: dict[str, list[tuple[str, int]]] = {}  # id -> [(texte du lien, fin du lien dans parser.texts)]
    starts: list[tuple[int, str]] = []  # (début du lien dans parser.texts, id) de chaque lien d'offre
    for href, text, start, end in parser.anchors:
        m = spec["pattern"].search(_unwrap(href))
        if not m:
            continue
        found.setdefault(m.group(1), []).append((text, end))
        starts.append((start, m.group(1)))

    jobs = []
    for jid, links in found.items():
        links = [(t, end) for t, end in links if len(t) >= 4 and not _NOISE.match(t)]
        if not links:
            continue
        texts = [t for t, _ in links]
        title, _, rest = texts[0].partition("\n")
        # « Entreprise · Lieu » : dans un 2e lien vers la même offre (ancien format LinkedIn)
        # ou sur la 2e ligne du lien de l'intitulé (France Travail).
        company = location = contract = ""
        for extra in [rest] + texts[1:]:
            extra = " · ".join(line for line in extra.split("\n") if line and line != title)
            if not extra:
                continue
            details = spec.get("details")
            m = details.fullmatch(extra) if details else None
            if m:
                company, location = m["company"] or "", m["location"]
            else:
                parts = re.split(r"\s+[·•|–-]\s+", extra, maxsplit=1)
                company = parts[0]
                location = parts[1] if len(parts) > 1 else ""
            break
        # Sinon, le texte qui suit le lien de l'intitulé, jusqu'au lien d'une autre offre.
        after = spec.get("after")
        if after and not (company or location):
            end = links[0][1]
            stop = min((s for s, other in starts if s >= end and other != jid), default=len(parser.texts))
            m = after.match("\n".join(parser.texts[end:stop][:6]))
            if m:
                info = m.groupdict()
                company, location, contract = (info.get(k) or "" for k in ("company", "location", "contract"))
        jobs.append(Job(source=site, source_id=jid, title=title,
                        url=spec["url"].format(id=jid), company=company,
                        location=location, contract=contract, from_alert=True))
    return jobs


def expired_alert(html: str, site: str) -> str | None:
    """Nom de l'alerte si l'e-mail annonce qu'elle a expiré (le site l'a alors supprimée)."""
    pattern = SITES[site].get("expired")
    m = pattern.search(clean_html(html)) if pattern else None
    return m.group(1) if m else None


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def _html_body(msg) -> str:
    html_part = text_part = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        content = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if ctype == "text/html" and html_part is None:
            html_part = content
        elif ctype == "text/plain" and text_part is None:
            text_part = content
    if html_part:
        return html_part
    # Repli texte brut : transforme les URL en liens pour réutiliser le même parseur.
    return re.sub(r"(https?://\S+)", r'<a href="\1">\1</a>', text_part or "")


class EmailAlertsSource:
    name = "email"

    def __init__(self, cfg: dict, user: str, password: str):
        self.cfg = cfg
        self.user = user
        self.password = password
        self.notices: list[tuple[str, str]] = []  # (clé unique, message) à envoyer une seule fois

    def folders(self, site: str) -> list[str]:
        """Dossiers IMAP du site ([email.folders] : un nom ou une liste), sinon le dossier commun `folder`."""
        folders = self.cfg.get("folders", {}).get(site) or self.cfg.get("folder", "INBOX")
        return [folders] if isinstance(folders, str) else list(folders)

    def _select(self, imap, folder: str) -> bool:
        typ, _ = imap.select(f'"{folder}"', readonly=True)
        if typ != "OK":
            log.warning("Dossier IMAP introuvable : %s", folder)
            return False
        return True

    def _messages(self, imap, site: str, since: str):
        """E-mails du site reçus depuis `since`, dans chacun de ses dossiers."""
        for folder in self.folders(site):
            if not self._select(imap, folder):
                continue
            for domain in self.cfg.get("senders", {}).get(site, []):
                typ, data = imap.search(None, "SINCE", since, "FROM", f'"{domain}"')
                if typ != "OK":
                    continue
                for num in data[0].split():
                    typ, msg_data = imap.fetch(num, "(BODY.PEEK[])")  # PEEK = ne marque pas lu
                    if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                        continue
                    yield email.message_from_bytes(msg_data[0][1])

    def fetch(self) -> list[Job]:
        host = self.cfg.get("host", "imap.gmail.com")
        port = int(self.cfg.get("port", 993))
        since = (datetime.now() - timedelta(days=int(self.cfg.get("lookback_days", 2)))).strftime("%d-%b-%Y")
        jobs: dict[str, Job] = {}
        self.notices = []
        with imaplib.IMAP4_SSL(host, port) as imap:
            imap.login(self.user, self.password)
            for site in self.cfg.get("senders", {}):
                if site not in SITES:
                    log.warning("Site d'alerte inconnu : %s", site)
                    continue
                for msg in self._messages(imap, site, since):
                    body = _html_body(msg)
                    extracted = extract_jobs(body, site)
                    log.debug("%s « %s » : %d offres", site, _decode(msg["Subject"]), len(extracted))
                    for j in extracted:
                        jobs.setdefault(j.key, j)
                    name = expired_alert(body, site)
                    if name:
                        key = f"{site}:{(msg['Message-ID'] or name).strip()}"
                        self.notices.append((key, SITES[site]["expired_message"].format(name=name)))
        log.info("Alertes e-mail : %d offres", len(jobs))
        return list(jobs.values())

    def debug_latest(self, site: str) -> None:
        """Affiche les liens du dernier e-mail d'un site, pour ajuster les motifs si besoin."""
        host = self.cfg.get("host", "imap.gmail.com")
        with imaplib.IMAP4_SSL(host, int(self.cfg.get("port", 993))) as imap:
            imap.login(self.user, self.password)
            for folder in self.folders(site):
                if not self._select(imap, folder):
                    print(f"Dossier IMAP introuvable : {folder}")
                    continue
                print(f"Dossier : {folder}")
                for domain in self.cfg.get("senders", {}).get(site, []):
                    typ, data = imap.search(None, "FROM", f'"{domain}"')
                    ids = data[0].split() if typ == "OK" else []
                    if not ids:
                        print(f"Aucun e-mail de {domain}")
                        continue
                    _, msg_data = imap.fetch(ids[-1], "(BODY.PEEK[])")
                    msg = email.message_from_bytes(msg_data[0][1])
                    body = _html_body(msg)
                    print(f"== {domain} — {_decode(msg['Subject'])}")
                    p = _AnchorParser()
                    p.feed(body)
                    for href, text, *_ in p.anchors:
                        print(f"- {text[:70]!r}\n    {_unwrap(href)[:160]}")
                    print(f"\nOffres reconnues : {len(extract_jobs(body, site))}")
                    for j in extract_jobs(body, site):
                        print(f"  * {j.title} | {j.company} | {j.location} | {j.url}")
                    if expired_alert(body, site):
                        print(f"Alerte expirée : {expired_alert(body, site)}")
