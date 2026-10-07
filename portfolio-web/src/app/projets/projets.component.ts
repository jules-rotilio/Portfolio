import { Component, DestroyRef, ElementRef, HostListener, Inject, OnInit, PLATFORM_ID, ViewChild } from '@angular/core';
import { isPlatformBrowser, NgFor } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { ProjectsService } from '../services/projects.service';
import { Project } from '../models/project';
import { ProjectDetailsComponent } from './project-details/project-details.component';

/** En dessous, la fiche détaillée n'est pas lisible : on propose d'ouvrir la page sur ordinateur. */
const MOBILE_QUERY = '(max-width: 767.98px)';

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
  /** Vrai sur un écran de téléphone : un petit message remplace la fiche détaillée. */
  isMobile = false;
  @ViewChild('noticeClose') set noticeClose(button: ElementRef<HTMLButtonElement> | undefined) {
    button?.nativeElement.focus();
  }

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
      this.updateIsMobile();
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

  @HostListener('window:resize')
  updateIsMobile(): void {
    this.isMobile = isPlatformBrowser(this.platformId) && window.matchMedia(MOBILE_QUERY).matches;
  }

  /** Échap ferme le message mobile ; la fiche détaillée gère sa propre touche Échap. */
  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.isMobile && this.openProject) {
      this.close();
    }
  }

  open(project: Project): void {
    this.router.navigate([], { relativeTo: this.route, queryParams: { projet: project.id } });
  }

  close(): void {
    this.router.navigate([], { relativeTo: this.route, queryParams: { projet: null } });
  }
}
