# Détail d'un projet : contrat d'API prévu

La page « Mes projets » ouvre une fenêtre de détail, présentée comme une page de dépôt GitHub, quand on clique sur une carte. L'URL porte l'ID du projet (`/projets?projet=5`), on peut donc partager le lien direct vers un projet.

Le front lit le détail dans cet ordre :

1. l'API (`GET /api/projects/{id}`), qui le construit à partir du dossier `project-content/{id}/` (voir [project-content/README.md](../project-content/README.md)) ;
2. à défaut, les données fictives `portfolio-web/public/mock/projects/{id}.json` (seul le projet 0, ce portfolio, en a) ;
3. à défaut, les informations de la carte.

## `GET /api/projects/{id}`

Renvoie le détail du projet, ou `404` s'il n'existe pas ou n'a pas de dossier de contenu. Les URL renvoyées (`images`, `files[].url`, `zipUrl`) sont relatives au domaine de l'API (`/api/projects/...`) : le front les complète avec `https://api.julesrotilio.fr`. Tous les champs du détail sont facultatifs : un champ absent reprend la valeur de la carte (ou une liste vide).

| Champ | Type | Description |
|---|---|---|
| `id` | `number` | ID du projet (le même que dans `/api/projects`) |
| `name` | `string` | Titre |
| `description` | `string` | Description courte, affichée sur la carte et dans « À propos » |
| `technologies` | `string[]` | Technologies, affichées comme des « topics » GitHub |
| `longDescription` | `string` | Description longue, affichée comme un README. Paragraphes séparés par une ligne vide ; un bloc dont toutes les lignes commencent par `- ` devient une liste. Texte brut, pas de HTML |
| `images` | `ProjectImage[]` | Aperçus de l'application, générés à l'avance |
| `files` | `ProjectFileNode[]` | Arborescence des fichiers sources |
| `zipUrl` | `string \| null` | Lien de l'archive .zip. Le bouton « Télécharger le .zip » n'apparaît que si ce champ est renseigné : l'API ne le remplit que pour les projets où le téléchargement est explicitement autorisé |
| `repoUrl` | `string \| null` | Lien vers un dépôt public, s'il existe |

### `ProjectImage`

| Champ | Type | Description |
|---|---|---|
| `url` | `string` | URL de l'image (de préférence JPEG ou WebP, 16:10) |
| `alt` | `string` | Texte alternatif |
| `caption` | `string?` | Légende affichée sous l'image |

### `ProjectFileNode`

| Champ | Type | Description |
|---|---|---|
| `name` | `string` | Nom du fichier ou du dossier |
| `path` | `string` | Chemin depuis la racine du projet, séparé par `/` (sert d'identifiant) |
| `type` | `"file" \| "directory"` | |
| `size` | `number?` | Taille en octets (fichiers) |
| `content` | `string?` | Contenu texte, affiché avec numéros de ligne. Absent pour les fichiers binaires ou trop volumineux |
| `url` | `string?` | URL du fichier brut : les images sont alors affichées dans la fenêtre |
| `children` | `ProjectFileNode[]?` | Contenu d'un dossier |

Le front trie lui-même les fichiers (dossiers d'abord, puis ordre alphabétique) et ouvre le `README` racine par défaut s'il a un contenu.

### Exemple

```json
{
  "id": 5,
  "longDescription": "Premier paragraphe.\n\n- Point clé 1\n- Point clé 2",
  "images": [{ "url": "/projects/5/bibliotheque.jpg", "alt": "Bibliothèque de médias", "caption": "Recherche par tags" }],
  "files": [
    { "name": "README.md", "path": "README.md", "type": "file", "size": 1200, "content": "# MediaToolkit\n..." },
    { "name": "src", "path": "src", "type": "directory", "children": [
      { "name": "main.py", "path": "src/main.py", "type": "file", "size": 830, "content": "..." }
    ] }
  ],
  "zipUrl": "https://api.julesrotilio.fr/api/projects/5/zip",
  "repoUrl": null
}
```

## Fichiers associés

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/projects/{id}/files/{chemin}` | Fichier source brut, seulement si `allowZipDownload` vaut `true` (sinon `404`). Les images sont affichées, les autres fichiers sont proposés en téléchargement |
| `GET` | `/api/projects/{id}/images/{nom}` | Aperçu de l'application |
| `GET` | `/api/projects/{id}/zip` | Archive .zip de `files/`, seulement si `allowZipDownload` vaut `true` dans `project.json` (sinon `404`) |

Le contenu des fichiers texte (UTF-8, 64 Ko au plus) est inclus dans `files[].content` ; les autres n'ont que leur `url`. Pour un projet sans `allowZipDownload`, l'arborescence est renvoyée sans `content` ni `url` : le site indique alors que le code n'est pas partagé.
