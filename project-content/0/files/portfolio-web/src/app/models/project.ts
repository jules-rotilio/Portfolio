/** Projet tel que renvoyé par GET /api/projects (carte de la page « Mes projets »). */
export interface Project {
  id: number;
  name: string;
  /** Description courte, affichée sur la carte. */
  description: string;
  technologies: string[];
}

/**
 * Détail d'un projet, affiché dans la fenêtre du projet.
 * Contrat prévu pour GET /api/projects/{id} (voir docs/api-project-details.md).
 */
export interface ProjectDetails extends Project {
  /** Description longue : paragraphes séparés par une ligne vide, lignes « - » pour les listes. */
  longDescription: string;
  /** Aperçus de l'application, générés à l'avance. */
  images: ProjectImage[];
  /** Arborescence des fichiers sources. */
  files: ProjectFileNode[];
  /** Lien de téléchargement de l'archive .zip, renseigné seulement si le projet l'autorise explicitement. */
  zipUrl?: string | null;
  /** Lien vers le dépôt public, s'il existe. */
  repoUrl?: string | null;
}

export interface ProjectImage {
  url: string;
  alt: string;
  caption?: string;
}

export interface ProjectFileNode {
  name: string;
  /** Chemin depuis la racine du projet, séparé par « / ». */
  path: string;
  type: 'file' | 'directory';
  /** Taille en octets (fichiers). */
  size?: number;
  /** Contenu texte du fichier ; absent pour les fichiers binaires ou trop volumineux. */
  content?: string | null;
  /** URL du fichier brut (images, binaires). */
  url?: string | null;
  children?: ProjectFileNode[];
}
