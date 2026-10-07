import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, map, of } from 'rxjs';
import { Project, ProjectDetails, ProjectFileNode } from '../models/project';

@Injectable({
  providedIn: 'root'
})
export class ProjectsService {
  private apiOrigin = 'http://localhost:20080';
  private apiUrl = `${this.apiOrigin}/api/projects`;

  constructor(private http: HttpClient) {}

  getProjects(): Observable<Project[]> {
    return this.http.get<Project[]>(this.apiUrl);
  }

  /**
   * Détail d'un projet, lu dans l'ordre :
   * 1. l'API (GET /api/projects/{id}), pour les projets dont le contenu est publié (dossier project-content/) ;
   * 2. les données fictives du front (public/mock/projects/{id}.json) ;
   * 3. à défaut, les informations de la carte.
   */
  getProjectDetails(project: Project): Observable<ProjectDetails> {
    const card = ProjectsService.fromProject(project);
    const mock$ = this.http.get<ProjectDetails>(`/mock/projects/${project.id}.json`).pipe(
      map((details) => ({ ...card, ...details })),
      catchError(() => of(card))
    );
    return this.http.get<ProjectDetails>(`${this.apiUrl}/${project.id}`).pipe(
      map((details) => this.withApiUrls({ ...card, ...details })),
      catchError(() => mock$)
    );
  }

  /** Détail minimal construit à partir de la carte : description longue = description courte, ni fichiers ni images. */
  static fromProject(project: Project): ProjectDetails {
    return { ...project, longDescription: project.description, images: [], files: [], zipUrl: null, repoUrl: null };
  }

  /** L'API renvoie des URL relatives à son domaine (/api/...) : le site étant sur un autre domaine, on les complète. */
  private withApiUrls(details: ProjectDetails): ProjectDetails {
    const absolute = (url: string) => (url.startsWith('/api/') ? this.apiOrigin + url : url);
    const files = (nodes: ProjectFileNode[]): ProjectFileNode[] =>
      nodes.map((n) => ({ ...n, url: n.url ? absolute(n.url) : n.url, children: n.children && files(n.children) }));
    return {
      ...details,
      images: details.images.map((i) => ({ ...i, url: absolute(i.url) })),
      files: files(details.files),
      zipUrl: details.zipUrl ? absolute(details.zipUrl) : details.zipUrl,
    };
  }
}
