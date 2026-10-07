import { AfterViewInit, Component, ElementRef, EventEmitter, Input, Output, ViewChild } from '@angular/core';
import { ProjectImage } from '../../models/project';

/** Aperçu affiché en grand, au-dessus de la fiche du projet. Échap et les flèches sont gérés par la fiche. */
@Component({
  selector: 'app-image-lightbox',
  templateUrl: './image-lightbox.component.html',
  styleUrl: './image-lightbox.component.scss'
})
export class ImageLightboxComponent implements AfterViewInit {
  @Input({ required: true }) images!: ProjectImage[];
  @Input({ required: true }) index!: number;
  @Output() indexChange = new EventEmitter<number>();
  @Output() closed = new EventEmitter<void>();
  @ViewChild('closeButton') closeButton?: ElementRef<HTMLButtonElement>;

  ngAfterViewInit(): void {
    this.closeButton?.nativeElement.focus();
  }
}
