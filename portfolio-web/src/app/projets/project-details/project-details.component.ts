import { AfterViewInit, Component, ElementRef, EventEmitter, HostListener, Inject, Input, OnChanges, OnDestroy, Output, ViewChild } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Subscription } from 'rxjs';
import { Project, ProjectDetails } from '../../models/project';
import { ProjectsService } from '../../services/projects.service';
import { FileBrowserComponent } from '../file-browser/file-browser.component';

export type DescriptionBlock = { type: 'paragraph'; text: string } | { type: 'list'; items: string[] };

/** Fenêtre de détail d'un projet, présentée comme une page de dépôt GitHub. */
@Component({
  selector: 'app-project-details',
  imports: [FileBrowserComponent],
  templateUrl: './project-details.component.html',
  styleUrl: './project-details.component.scss'
})
export class ProjectDetailsComponent implements OnChanges, AfterViewInit, OnDestroy {
  @Input({ required: true }) project!: Project;
  @Output() closed = new EventEmitter<void>();
  @ViewChild('closeButton') closeButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('fileBrowser') fileBrowser?: FileBrowserComponent;
  @ViewChild('thumbnails') thumbnails?: ElementRef<HTMLElement>;
  @ViewChild('lightboxClose') lightboxClose?: ElementRef<HTMLButtonElement>;

  details: ProjectDetails | null = null;
  description: DescriptionBlock[] = [];
  imageIndex = 0;
  lightboxOpen = false;
  private subscription?: Subscription;
  private previousFocus: Element | null;

  constructor(private projectsService: ProjectsService, @Inject(DOCUMENT) private document: Document) {
    this.previousFocus = document.activeElement;
    // Classe Bootstrap : bloque le défilement de la page derrière la fenêtre
    document.body.classList.add('modal-open');
  }

  ngOnChanges(): void {
    this.subscription?.unsubscribe();
    this.details = null;
    this.imageIndex = 0;
    this.lightboxOpen = false;
    this.subscription = this.projectsService.getProjectDetails(this.project).subscribe((details) => {
      this.details = details;
      this.description = parseDescription(details.longDescription);
    });
  }

  ngAfterViewInit(): void {
    this.closeButton?.nativeElement.focus();
  }

  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
    this.document.body.classList.remove('modal-open');
    (this.previousFocus as HTMLElement | null)?.focus?.();
  }

  /** Échap ferme d'abord la fenêtre la plus haute : image agrandie, puis code agrandi, puis la fiche. */
  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.lightboxOpen) {
      this.closeLightbox();
    } else if (this.fileBrowser?.expanded) {
      this.fileBrowser.setExpanded(false);
    } else {
      this.close();
    }
  }

  @HostListener('document:keydown', ['$event'])
  onArrow(event: KeyboardEvent): void {
    if (this.lightboxOpen && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      this.showImage(this.imageIndex + (event.key === 'ArrowLeft' ? -1 : 1));
    }
  }

  close(): void {
    this.closed.emit();
  }

  showImage(index: number): void {
    const count = this.details?.images.length ?? 0;
    if (count) {
      this.imageIndex = (index + count) % count;
      this.scrollThumbnailIntoView();
    }
  }

  openLightbox(): void {
    this.lightboxOpen = true;
    setTimeout(() => this.lightboxClose?.nativeElement.focus());
  }

  closeLightbox(): void {
    this.lightboxOpen = false;
  }

  /** Fait défiler la bande de miniatures pour centrer celle de l'image affichée. */
  private scrollThumbnailIntoView(): void {
    const strip = this.thumbnails?.nativeElement;
    const thumbnail = strip?.children.item(this.imageIndex) as HTMLElement | null | undefined;
    if (strip && thumbnail && typeof strip.scrollTo === 'function') {
      const left = thumbnail.offsetLeft - (strip.clientWidth - thumbnail.offsetWidth) / 2;
      strip.scrollTo({ left: Math.max(0, left), behavior: 'smooth' });
    }
  }
}

/** Paragraphes séparés par une ligne vide ; les lignes commençant par « - » forment une liste. */
export function parseDescription(text: string): DescriptionBlock[] {
  return text
    .split(/\r?\n\s*\r?\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block): DescriptionBlock => {
      const lines = block.split(/\r?\n/).map((l) => l.trim());
      return lines.every((l) => l.startsWith('- '))
        ? { type: 'list', items: lines.map((l) => l.slice(2)) }
        : { type: 'paragraph', text: lines.join(' ') };
    });
}
