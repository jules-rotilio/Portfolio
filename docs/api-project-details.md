# Détail d'un projet : contrat d'API prévu

La page « Mes projets » ouvre une fenêtre de détail, présentée comme une page de dépôt GitHub, quand on clique sur une carte. L'URL porte l'ID du projet (`/projets?projet=5`), on peut donc partager le lien direct vers un projet.

L'API ne renvoie pas encore ce détail. En attendant, le front lit des données fictives dans `portfolio-web/public/mock/projects/{id}.json` (seul le projet 0, ce portfolio, en a pour l'instant). Pour les autres projets, la fenêtre reprend les informations de la carte.

**Pour brancher l'API :** implémenter la route ci-dessous, puis passer `ProjectsService.useMockDetails` à `false` dans `portfolio-web/src/app/services/projects.service.ts`. Les types TypeScript correspondants sont dans `portfolio-web/src/app/models/project.ts`.

## `GET /api/projects/{id}`

Renvoie le détail du projet, ou `404` s'il n'existe pas. Tous les champs du détail sont facultatifs : un champ absent reprend la valeur de la carte (ou une liste vide).

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

Le contenu des fichiers peut peser lourd : si besoin, l'API pourra plus tard ne renvoyer que l'arborescence et servir chaque fichier à part (`url`), le front affichant déjà `content` ou l'image `url` selon ce qui est présent.
