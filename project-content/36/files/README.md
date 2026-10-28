# Enceinte Bose SoundTouch sans le cloud Bose

Bose a arrêté les services cloud des enceintes SoundTouch en mai 2026 : radios intégrées, synchronisation des présélections et du compte. Pour continuer à utiliser ma SoundTouch 10, j'héberge sur mon serveur domestique **AfterTouch**, un remplaçant open source de ce cloud.

Je ne suis pas l'auteur d'AfterTouch : il est développé par Tobias Gesellchen et ses contributeurs, sous licence MIT ([gesellix/Bose-SoundTouch](https://github.com/gesellix/Bose-SoundTouch)). Ce dossier contient uniquement ma configuration de déploiement et un petit script d'observation.

## Fichiers

- `docker-compose.yml` : construit et lance le service à partir du code source relu, et non de l'image publiée
- `env.example` : variables à copier dans `.env` (adresse du serveur, sous-réseau, mot de passe d'administration, application Spotify)
- `ws_listen.py` : écoute les événements que l'enceinte envoie en direct par WebSocket (port 8080, sous-protocole `gabbo`)

## Démarche

1. **Exploration en lecture seule** : avant d'utiliser AfterTouch, j'ai scanné les ports, fait des relevés de l'API HTTP/XML locale (port 8090), récupéré des événements WebSocket et lancé des commandes en lecture seule sur la console de diagnostic (port 17000) pour faire des backups.
2. **Revue du code** avant de l'exécuter : appels réseau sortants, clés embarquées, commandes envoyées à l'enceinte, étapes de build, valeurs par défaut. Aucun comportement malveillant détecté ; deux points corrigés dans ma configuration (mot de passe d'administration par défaut, interface d'administration ouverte sans authentification).
3. **Déploiement** sur mon serveur Docker: ports liés à l'adresse LAN uniquement, authentification activée sur toute l'interface d'administration.
4. **Migration** de l'enceinte : ses quatre URL de service (compte, registre des services musicaux, mises à jour, statistiques) pointent maintenant vers mon serveur. J'ai vérifié qu'elles restaient en place après un redémarrage à l'aide du guide.
5. **Nettoyage** des sources de l'enceinte : la liste s'était remplie de doublons, faute de pouvoir se synchroniser avec le cloud. J'ai aussi retiré les comptes obsolètes, côté enceinte et côté serveur.
6. **Spotify** : application créée sur le tableau de bord développeur Spotify, avec une redirection OAuth en https, pour que l'enceinte puisse lire des playlists Spotify depuis ses boutons de présélection.

## Lancer

```
git clone https://github.com/gesellix/Bose-SoundTouch.git vendor/Bose-SoundTouch
cp env.example .env && chmod 600 .env   # puis renseigner les valeurs
docker compose up -d --build
```

L'application est disponible à l'adresse `http://<HOST_IP>:8000`.
L'interface d'administration est ensuite sur `http://<HOST_IP>:8000/admin`.
Le lecteur est disponible à l'adresse `http://<HOST_IP>:8000/app`.