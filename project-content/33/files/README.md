# jobwatch — veille d'offres d'emploi vers Discord

Toutes les 30 minutes, `jobwatch` récupère les nouvelles offres, garde celles qui correspondent à **C#/.NET, Python ou DevOps**, et les poste dans un salon Discord : tu reçois une notification push sur ton téléphone.

Python 3.11+, **aucune dépendance** (bibliothèque standard uniquement).

## Sources

| Source | Comment | Ce qu'il faut |
| --- | --- | --- |
| **LinkedIn, Indeed, HelloWork, France Travail** | Lecture (IMAP, en lecture seule) des alertes e-mail que tu crées sur chaque site | Une boîte mail + un mot de passe d'application |

Pourquoi pas d'aspiration directe des sites : LinkedIn, Indeed et HelloWork n'ont pas d'API publique, l'interdisent dans leurs conditions d'utilisation et bloquent les robots (LinkedIn peut suspendre ton compte). Les alertes e-mail donnent les mêmes offres, proprement.

## Fonctionnement

1. Chaque source renvoie ses offres récentes.
2. Les offres déjà vues sont ignorées (SQLite, `data/jobs.db`), y compris la même offre publiée sur deux sources (même intitulé + même entreprise).
3. Filtre :
   - l'intitulé doit mentionner C#/.NET, Python ou DevOps ;
   - si l'intitulé est générique (« Analyste développeur »), la description est examinée ;
   - les intitulés contenant senior, lead, stage, alternance… sont exclus (modifiable) ;
   - les offres des alertes e-mail sont gardées même si l'intitulé est vague, puisque le site les a déjà filtrées.
4. Les nouvelles offres partent sur Discord, un message par offre (entreprise, lieu et contrat quand ils sont connus, couleur selon la source, étiquette C#/.NET, Python ou DevOps).
5. Au tout premier lancement, seules les 15 plus récentes sont envoyées, pour ne pas inonder le salon.

Si la lecture des e-mails échoue (serveur IMAP injoignable, mot de passe refusé…), un message d'avertissement arrive sur Discord. Quand France Travail supprime une alerte arrivée à échéance, un rappel arrive aussi sur Discord pour la recréer.

## Installation

### 1. Discord

Sur ton serveur Discord : crée un salon `#offres`, puis **Paramètres du salon › Intégrations › Webhooks › Nouveau webhook › Copier l'URL**.
Sur ton téléphone, règle les notifications de ce salon sur **Tous les messages**.

### 2. Alertes e-mail (LinkedIn, Indeed, HelloWork, France Travail)

- Crée une alerte sur chaque site (ex. « développeur C# », « python », « devops », avec Lyon, Paris, Saône-et-Loire, télétravail), en **fréquence quotidienne ou instantanée**.
- France Travail : lance une recherche sur https://candidat.francetravail.fr/offres/recherche, puis « Créer une alerte » (un mot-clé par alerte, ex. `C#`, `.NET`, `Python`, `DevOps`). Ces alertes expirent au bout d'un an : jobwatch te prévient sur Discord quand il faut les recréer.
- Gmail : active la validation en 2 étapes, puis crée un **mot de passe d'application** (compte Google › Sécurité). Utilise-le comme `IMAP_PASSWORD`.
- Facultatif : un filtre Gmail qui range ces e-mails sous un libellé `Alertes emploi`, à indiquer dans `config.toml` (`folder = "Alertes emploi"`).
- Si chaque site a son propre dossier, indique-les dans `[email.folders]` : un nom (ex. `linkedin = "INBOX/Jobs/Linkedin"`) ou une liste de dossiers à lire (ex. `francetravail = ["INBOX/Jobs/France Travail", "INBOX"]`). Le séparateur de sous-dossiers dépend du serveur (`/` ou `.`).

Les e-mails ne sont ni supprimés ni marqués comme lus.

### 3. Lancer sur le serveur Debian (Docker)

```bash
git clone <ton-repo> jobwatch && cd jobwatch
cp .env.example .env && nano .env        # remplis les secrets
nano config.toml                         # boîte mail, dossiers, catégories, exclusions
mkdir -p data && sudo chown 1000:1000 data
docker compose run --rm jobwatch python -m jobwatch --config /app/config.toml --test-webhook     # message de test sur Discord
docker compose run --rm jobwatch python -m jobwatch --config /app/config.toml --once --dry-run   # test sans envoi
docker compose up -d --build
docker compose logs -f
```

### Sans Docker (cron ou systemd)

```bash
python3 -m jobwatch --once            # un passage
python3 -m jobwatch                    # boucle toutes les 30 min
```

Avec cron, toutes les 30 minutes :

```cron
*/30 * * * * cd /opt/jobwatch && /usr/bin/python3 -m jobwatch --once >> /var/log/jobwatch.log 2>&1
```

## Commandes utiles

| Commande | Rôle |
| --- | --- |
| `--once` | Un seul passage puis sortie |
| `--dry-run` | Affiche les messages Discord au lieu de les envoyer |
| `--test-webhook` | Envoie un message de test sur Discord (mention + carte d'exemple), sans lire de source ni toucher à la base |
| `--debug-email linkedin` | Montre les liens du dernier e-mail d'alerte LinkedIn et les offres reconnues (idem `indeed`, `hellowork`, `francetravail`) |
| `-v` | Logs détaillés |

Si un site change le format de ses e-mails et qu'une alerte ne donne plus d'offres, lance `--debug-email <site>` puis ajuste le motif correspondant dans `jobwatch/sources/email_alerts.py` (dictionnaire `SITES`).

## Réglages (`config.toml`)

- `filters.categories` : `csharp`, `python`, `devops`
- `filters.exclude_title` : intitulés à écarter (regex sur texte en minuscules sans accents)
- `discord.mention` : `"<@ton_id_discord>"` pour être mentionné à chaque nouvelle offre

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
