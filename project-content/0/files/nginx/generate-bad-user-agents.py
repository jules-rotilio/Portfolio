#!/usr/bin/env python3
"""Génère nginx/bad_user_agents.conf à partir de la liste mthcht/awesome-lists.

Usage : python3 nginx/generate-bad-user-agents.py [liste.csv]
Sans argument, la liste est téléchargée depuis GitHub.

La liste d'origine est faite pour la détection (SIEM) : elle contient des motifs trop généraux
pour du blocage (navigateurs Linux, wget, curl, vieux Chrome...). On ne garde donc que :
  - les entrées à faible risque de faux positif (fp_risk = none ou low),
  - d'au moins 6 caractères utiles et qui ne sont pas un mot courant (GENERIC),
  - qui ne correspondent à aucun des clients légitimes listés dans LEGIT ci-dessous.
Chaque entrée est cherchée comme sous-chaîne du User-Agent (insensible à la casse), '*' = n'importe quoi.
"""
import csv
import io
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/mthcht/awesome-lists/refs/heads/main/Lists/suspicious_http_user_agents_list.csv"
OUT = Path(__file__).with_name("bad_user_agents.conf")
MIN_LENGTH = 6
# nginx refuse un paramètre de plus de 4096 caractères : on découpe en plusieurs expressions
CHUNK = 3000

# Motifs ajoutés à la main (outils connus, scrapers SEO, crawlers d'IA), ajoutés tels quels à la liste.
# Pas de curl/wget/python-requests ici, pour ne pas bloquer les tests et sondes de santé.
EXTRA = [
    "sqlmap", "nikto", "masscan", "nmap", "zgrab", "nuclei", "acunetix", "wpscan", "dirbuster", "gobuster",
    "havij", "scrapy", "python-urllib", "libwww-perl",
    "semrush", "ahrefs", "mj12bot", "dotbot", "petalbot", "bytespider", "blexbot", "dataforseo", "megaindex",
    "gptbot", "chatgpt-user", "oai-searchbot", "ccbot", "claudebot", "anthropic-ai", "perplexitybot",
    "amazonbot", "meta-externalagent",
]

# Mots courants de la liste qui, cherchés comme sous-chaîne, risquent de bloquer des visiteurs ordinaires
GENERIC = {
    "accessing", "attach", "bullseye", "bundle", "collector", "cosmos", "crescent", "counters", "curious",
    "default", "dispatch", "downloader", "dragonfly", "example", "explorer", "extractor", "fetcher", "fucking",
    "gopher", "hacker", "harvest", "iexplore", "installer", "internet", "joomla", "magnet", "momentum",
    "needle", "octopus", "presto", "reaper", "record", "recorder", "ripper", "session", "spanner", "stripper",
    "sucker", "suggestion", "svchost", "toolbar", "undici", "update", "updater", "uploader", "vaccine",
    "wallpapers", "webdav", "webster", "windowsnt", "winlogon",
}

# Clients légitimes qui ne doivent jamais être bloqués (navigateurs, robots utiles, clients mail, sondes)
LEGIT = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.0.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 14; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Mozilla/5.0 (compatible; DuckDuckBot-Https/1.1; https://duckduckgo.com/duckduckbot)",
    "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
    "Mozilla/5.0 (compatible; Qwantbot/1.0; +https://help.qwant.com/bot/)",
    "Mozilla/5.0 (compatible; Applebot/0.1; +http://www.apple.com/go/applebot)",
    "Mozilla/5.0 (compatible; Let's Encrypt validation server; +https://www.letsencrypt.org)",
    "Mozilla/5.0 (compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "Slack-ImgProxy (+https://api.slack.com/robots)",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Twitterbot/1.0",
    "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
    "WhatsApp/2.23.20.0",
    "TelegramBot (like TwitterBot)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Lighthouse",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Thunderbird/128.4.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Thunderbird/128.4.0",
    "Microsoft Office/16.0 (Windows NT 10.0; Microsoft Outlook 16.0.17928; Pro)",
    "Outlook-Android/2.0",
    "Apple-iPhone15C3/2101.100",
    "iOS/18.0 (22A3354) dataaccessd/1.0",
    "Mail/3826.100.6 CFNetwork/1568.100.1 Darwin/24.0.0",
    "DAVx5/4.4.4-ose (2024/10/01; dav4jvm; okhttp/4.12.0) Android/14",
    "Android-Mail/1.0",
    "okhttp/4.12.0",
    "Dalvik/2.1.0 (Linux; U; Android 14; Pixel 8 Build/AP2A.240905.003)",
    "curl/8.5.0",
    "Wget/1.21.4",
    "python-requests/2.32.3",
    "Go-http-client/2.0",
    "node",
    "axios/1.7.7",
    "PostmanRuntime/7.43.0",
    "Java/17.0.12",
]


def to_regex(entry: str) -> str:
    """'*' devient '.*', tout le reste est littéral. Les '*' de début et de fin sont inutiles (recherche de sous-chaîne)."""
    return ".*".join(re.escape(part) for part in entry.strip("*").split("*"))


def to_nginx_string(regex: str) -> str:
    """Entre guillemets, nginx lit \\\\ comme \\ et \\\" comme \" : on double les antislashs."""
    return '"' + regex.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load_rows():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(URL, timeout=30) as response:
            text = response.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    rows = load_rows()
    kept, dropped_legit, skipped = {}, [], 0
    for row in rows:
        entry = row["http_user_agent"].strip()
        useful = entry.replace("*", "")
        if (row["metadata_fp_risk"] not in ("none", "low") or len(useful) < MIN_LENGTH
                or not entry.isascii() or entry.lower() in GENERIC):
            skipped += 1
            continue
        regex = to_regex(entry)
        compiled = re.compile(regex, re.IGNORECASE)
        hit = next((ua for ua in LEGIT if compiled.search(ua)), None)
        if hit:
            dropped_legit.append((entry, hit))
            continue
        kept[regex.lower()] = regex  # dédoublonnage insensible à la casse

    for entry in EXTRA:
        regex = to_regex(entry)
        compiled = re.compile(regex, re.IGNORECASE)
        hit = next((ua for ua in LEGIT if compiled.search(ua)), None)
        if hit:
            sys.exit(f"Le motif ajouté à la main {entry!r} bloquerait un client légitime : {hit!r}")
        kept[regex.lower()] = regex

    regexes = sorted(kept.values())
    chunks, current, size = [], [], 0
    for regex in regexes:
        escaped_size = len(to_nginx_string(regex)) + 1
        if size + escaped_size > CHUNK and current:
            chunks.append(current)
            current, size = [], 0
        current.append(regex)
        size += escaped_size
    if current:
        chunks.append(current)

    lines = [
        "# Fichier généré par nginx/generate-bad-user-agents.py : ne pas modifier à la main.",
        f"# Source : {URL}",
        f"# {len(regexes)} motifs : liste filtrée (faible risque de faux positif) sur {len(rows)} entrées + motifs ajoutés à la main.",
        "# Contenu complet du bloc `map $http_user_agent $bad_bot` de nginx.conf (inclus avec `include`).",
        "",
        "default 0;",
        '"" 1;  # pas de User-Agent du tout',
        "",
    ]
    for chunk in chunks:
        lines.append('"~*' + "|".join(to_nginx_string(r)[1:-1] for r in chunk) + '" 1;')
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(rows)} entrées lues, {skipped} ignorées (risque de faux positif, trop courtes ou trop générales), "
          f"{len(dropped_legit)} retirées car elles bloqueraient un client légitime, {len(regexes)} écrites.")
    for entry, hit in dropped_legit:
        print(f"  retiré : {entry!r} (aurait bloqué {hit[:70]!r})")


if __name__ == "__main__":
    main()
