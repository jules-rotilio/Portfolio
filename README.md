# Portfolio Jules ROTILIO

Code source de mon portfolio, [julesrotilio.fr](https://julesrotilio.fr) : un front Angular rendu côté serveur, une API ASP.NET Core et un reverse proxy nginx, orchestrés avec Docker Compose.

Le site présente mon CV et mes projets, et propose un formulaire de contact qui m'envoie un e-mail via mon serveur mail auto-hébergé ([mailcow](https://mailcow.email)).

## Technologies

- **Front** : Angular 19 avec SSR et prérendu (`@angular/ssr`), servi par Express ; Bootstrap 5 et SCSS
- **API** : ASP.NET Core (.NET 10), MailKit pour l'envoi SMTP, OpenAPI, limitation de débit intégrée
- **Infra** : Docker Compose, nginx, mailcow
- **Tests** : xUnit et `WebApplicationFactory` (API), Karma et Jasmine (front)

## Architecture

```text
                   ┌── julesrotilio.fr ──────→ web  (Angular SSR + Express)
Visiteur ──→ nginx ┼── api.julesrotilio.fr ──→ api  (ASP.NET Core) ──SMTP──→ mailcow
                   └── mail.rotilio.fr ──────→ mailcow
```

| Service | Rôle | Port hôte |
|---|---|---|
| `nginx` | Point d'entrée : TLS, redirection HTTP → HTTPS, limites de débit, en-têtes de sécurité, routage par nom d'hôte | 9080 (HTTP), 9443 (HTTPS) |
| `web` | Front Angular servi par Express en HTTPS (`/`, `/cv`, `/projets`, `/contact`) | 4443 |
| `api` | API ASP.NET Core en HTTPS | 8443 |

nginx sert aussi de point d'entrée au serveur mail (`mail.rotilio.fr`, autoconfig, autodiscover) en le joignant par le réseau Docker de mailcow.

### API

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/projects` | Liste des projets, lue depuis `Portfolio.Api/Projects.json` |
| `POST` | `/api/send-email` | Envoie un message du formulaire de contact (`from`, `subject`, `body`) |
| `GET` | `/api/projects/{id}` | Détail d'un projet (description longue, aperçus, fichiers, lien .zip), lu depuis `project-content/{id}/`. Voir [docs/api-project-details.md](docs/api-project-details.md) |

Pour ajouter un projet, éditer `Portfolio.Api/Projects.json` (`ID` unique, `Name`, `Description`, `Technologies`) puis reconstruire l'API (`docker compose up -d --build api`). Les tests vérifient qu'aucun champ ne manque et que les ID sont uniques.

## Structure du dépôt

```text
.
├── Portfolio.Api/         API ASP.NET Core (.NET 10)
├── Portfolio.Api.Tests/   Tests d'intégration xUnit de l'API
├── portfolio-web/         Front Angular 19 (SSR)
├── nginx/                 Configuration du reverse proxy
├── project-content/       Fichiers sources et aperçus des projets, servis par l'API
├── certs/                 Certificats TLS (hors Git, à fournir)
├── docker-compose.yml
└── PortfolioSolution.sln  Solution .NET (API + tests)
```

## Configuration

Deux éléments sont volontairement **absents du dépôt** (voir `.gitignore`) et à fournir avant de lancer la pile.

**`Portfolio.Api/.env`** : identifiants du compte SMTP utilisé par le formulaire de contact.

```env
SMTP_U=<utilisateur du compte SMTP>
SMTP_P=<mot de passe du compte SMTP>
```

**`certs/`** : certificats TLS au format PEM, montés en lecture seule dans les conteneurs et jamais copiés dans les images.

| Fichiers | Utilisés pour |
|---|---|
| `julesrotilio.fr-crt.pem`, `julesrotilio.fr-key.pem`, `julesrotilio.fr-chain.pem` | le site et l'API (`julesrotilio.fr`, `api.julesrotilio.fr`) |
| `rotilio.fr-crt.pem`, `rotilio.fr-key.pem`, `rotilio.fr-chain.pem` | le serveur mail (`rotilio.fr`, `mail.rotilio.fr`, autoconfig, autodiscover) |

Le réseau Docker externe `mailcowdockerized_mailcow-network` doit exister (mailcow-dockerized installé et démarré sur la machine), sinon `docker compose up` échoue.

L'hôte SMTP, l'expéditeur et le destinataire des messages sont des constantes de `Portfolio.Api/Services/ContactMailer.cs` ; l'origine CORS autorisée est définie dans `Portfolio.Api/Program.cs`.

## Démarrage avec Docker Compose

Prérequis : Docker avec Compose v2.

```bash
docker compose up -d --build
```

nginx route les requêtes selon le nom d'hôte ; `web` et `api` sont aussi publiés directement sur leurs ports.

## Développement local

### API

Prérequis : SDK .NET 10.

```bash
dotnet run --project Portfolio.Api --launch-profile https   # https://localhost:20443
```

En développement, la spécification OpenAPI est exposée sur `/openapi/v1.json`. Pour tester l'envoi d'e-mails, définir `SMTP_U` et `SMTP_P` en variables d'environnement (le fichier `.env` n'est lu que par Docker Compose).

### Front

Prérequis : Node.js 22. Les commandes Angular CLI sont détaillées dans [portfolio-web/README.md](portfolio-web/README.md).

```bash
cd portfolio-web
npm install
npm start   # http://localhost:4200
```

En production, les services `projects.service.ts` et `contact.service.ts` appellent `https://api.julesrotilio.fr`. En développement (`ng serve`), ils appellent des URL relatives (`/api/...`, voir `src/environments/environment.development.ts`) que le serveur de développement transmet à l'API locale : le navigateur ne parle qu'à `localhost:4200`, la politique CORS de l'API ne s'applique donc pas. Le fichier de proxy n'est pas versionné ; le créer dans `portfolio-web/proxy.conf.json` :

```json
{ "/api": { "target": "http://localhost:20080", "secure": false, "changeOrigin": true } }
```

Puis lancer l'API (`dotnet run --project Portfolio.Api --launch-profile http`, depuis la racine) et le front avec `npm start -- --proxy-config proxy.conf.json`.

## Tests

```bash
dotnet test PortfolioSolution.sln
cd portfolio-web && npm test -- --watch=false --browsers=ChromeHeadlessCI
```

Les tests de l'API couvrent la validation du formulaire, la limite d'envoi, la politique CORS et l'encodage HTML des messages. Les tests du front nécessitent Chrome ou Chromium.

## Sécurité

- **nginx** : TLS 1.2 et 1.3 uniquement (profil « intermediate » de Mozilla), HSTS, CSP et autres en-têtes de sécurité, méthodes HTTP restreintes, limites de débit et de connexions par IP, rejet des requêtes dont le nom d'hôte n'est pas déclaré, fichiers cachés (`.env`, `.git`…) jamais servis.
- **API** : formulaire de contact limité à 5 messages par heure et par IP, validation stricte des champs, contenu du visiteur encodé avant insertion dans l'e-mail, CORS restreint au site, détails d'erreur SMTP jamais renvoyés au visiteur.
- **Proxy de confiance** : l'API n'accepte `X-Forwarded-For` que s'il provient du conteneur nginx (`TRUSTED_PROXY`, IP fixe définie dans `docker-compose.yml`), ce qui empêche de contourner la limite d'envoi en falsifiant l'en-tête.
- **Secrets** : `.env` et `certs/` sont exclus de Git (`.gitignore`) et des images Docker (`.dockerignore`).
