import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, map, of } from 'rxjs';
import { Project, ProjectDetails } from '../models/project';

@Injectable({
  providedIn: 'root'
})
export class ProjectsService {
  private apiUrl = 'https://api.julesrotilio.fr/api/projects';

  /**
   * En attendant que l'API renvoie le détail des projets (GET /api/projects/{id}),
   * le détail est lu depuis des données fictives servies par le front (public/mock/projects/{id}.json).
   * Passer à false une fois l'API prête.
   */
  static readonly useMockDetails = true;

  constructor(private http: HttpClient) {}

  getProjects(): Observable<Project[]> {
    return this.http.get<Project[]>(this.apiUrl);
  }

  /**
   * Détail d'un projet. Si le détail n'existe pas (encore), la fenêtre affiche les informations de la carte.
   */
  getProjectDetails(project: Project): Observable<ProjectDetails> {
    const url = ProjectsService.useMockDetails ? `/mock/projects/${project.id}.json` : `${this.apiUrl}/${project.id}`;
    return this.http.get<ProjectDetails>(url).pipe(
      map((details) => ({ ...ProjectsService.fromProject(project), ...details })),
      catchError(() => of(ProjectsService.fromProject(project)))
    );
  }

  /** Détail minimal construit à partir de la carte : description longue = description courte, ni fichiers ni images. */
  static fromProject(project: Project): ProjectDetails {
    return { ...project, longDescription: project.description, images: [], files: [], zipUrl: null, repoUrl: null };
  }
}
