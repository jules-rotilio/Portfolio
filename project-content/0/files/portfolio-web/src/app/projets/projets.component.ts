import { Component, DestroyRef, Inject, OnInit, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser, NgFor } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { ProjectsService } from '../services/projects.service';
import { Project } from '../models/project';
import { ProjectDetailsComponent } from './project-details/project-details.component';

@Component({
  selector: 'app-projets',
  imports: [NgFor, ProjectDetailsComponent],
  templateUrl: './projets.component.html',
  styleUrl: './projets.component.scss'
})
export class ProjetsComponent implements OnInit {
  projects: Project[] = [];
  projectRows: Project[][] = [];
  /** ID du projet ouvert dans la fenêtre de détail, d'après le paramètre ?projet=ID de l'URL. */
  selectedId: number | null = null;

  constructor(
    private projectsService: ProjectsService,
    private route: ActivatedRoute,
    private router: Router,
    private destroyRef: DestroyRef,
    @Inject(PLATFORM_ID) private platformId: object
  ) {}

  ngOnInit(): void {
    this.projectsService.getProjects().subscribe({
      next: (data) => {
        this.projects = data;
        this.projectRows = [];
        for (let i = 0; i < this.projects.length; i += 2) {
          this.projectRows.push(this.projects.slice(i, i + 2));
        }
      },
      error: (err) => console.error(err)
    });

    // La fenêtre n'est ouverte que dans le navigateur (pas de rendu côté serveur)
    if (isPlatformBrowser(this.platformId)) {
      this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
        const id = params.get('projet');
        this.selectedId = id === null ? null : Number(id);
      });
    }
  }

  /** Le lien peut arriver avant la liste des projets : la fenêtre s'ouvre dès que le projet est connu. */
  get openProject(): Project | null {
    return this.projects.find((p) => p.id === this.selectedId) ?? null;
  }

  open(project: Project): void {
    this.router.navigate([], { relativeTo: this.route, queryParams: { projet: project.id } });
  }

  close(): void {
    this.router.navigate([], { relativeTo: this.route, queryParams: { projet: null } });
  }
}
