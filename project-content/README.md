# Contenu détaillé des projets

Ce dossier est lu par l'API (`GET /api/projects/{id}`) pour remplir la fenêtre de détail d'un projet. Il est monté dans le conteneur `api` (`/app/project-content`, en lecture seule). En développement, l'API le lit via `ProjectContent:Path` (`appsettings.Development.json`).

Un sous-dossier par projet, nommé d'après son `ID` dans `Portfolio.Api/Projects.json` :

```text
project-content/
└── 5/                     MediaToolkit
    ├── project.json       description longue, aperçus, autorisation du .zip
    ├── files/             fichiers sources, affichés dans l'arborescence
    └── images/            aperçus de l'application
```

`project.json` (tous les champs sont facultatifs) :

```json
{
  "longDescription": "Premier paragraphe.\n\n- Point clé 1\n- Point clé 2",
  "images": [{ "file": "bibliotheque.jpg", "alt": "Bibliothèque de médias", "caption": "Recherche par tags" }],
  "allowZipDownload": true,
  "repoUrl": null
}
```

Tout ce qui est dans `files/` devient **public**. Ne copier ni secrets, ni environnement virtuel, ni caches. Par sécurité, l'API ignore de toute façon `.env*`, `.git`, `venv`, `.venv`, `env`, `__pycache__`, `site-packages`, `node_modules`, `bin`, `obj`, les dossiers d'IDE et les liens symboliques. Sans `"allowZipDownload": true`, le code n'est pas partagé : l'arborescence reste visible, mais ni le contenu des fichiers ni le .zip ne sont servis. Les fichiers texte de plus de 64 Ko ou non UTF-8 apparaissent dans l'arborescence sans aperçu.

Un projet sans dossier ici renvoie `404` : le site affiche alors ses données fictives (`portfolio-web/public/mock/projects/{id}.json`) s'il en a, sinon les informations de sa carte.
