import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { parseDescription, ProjectDetailsComponent } from './project-details.component';

const CARD = { id: 2, name: 'Mon projet', description: 'Description courte', technologies: ['Angular', 'C#'] };

describe('ProjectDetailsComponent', () => {
  let fixture: ComponentFixture<ProjectDetailsComponent>;
  let http: HttpTestingController;
  let element: HTMLElement;

  function open(details: object | null) {
    fixture.componentRef.setInput('project', CARD);
    fixture.detectChanges();
    const req = http.expectOne('/mock/projects/2.json');
    if (details) {
      req.flush(details);
    } else {
      req.flush('', { status: 404, statusText: 'Not Found' });
    }
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProjectDetailsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(ProjectDetailsComponent);
    http = TestBed.inject(HttpTestingController);
    element = fixture.nativeElement;
  });

  afterEach(() => {
    http.verify();
    fixture.destroy();
  });

  it('présente le projet comme un dépôt : titre, technologies, description longue', () => {
    open({ id: 2, longDescription: 'Premier paragraphe.\n\n- Point A\n- Point B' });

    expect(element.querySelector('h2')?.textContent).toContain('Mon projet');
    expect(Array.from(element.querySelectorAll('.topics li')).map((t) => t.textContent)).toEqual(['Angular', 'C#']);
    expect(element.querySelector('.about p')?.textContent).toBe('Description courte');
    expect(element.querySelector('.readme p')?.textContent).toBe('Premier paragraphe.');
    expect(Array.from(element.querySelectorAll('.readme li')).map((l) => l.textContent)).toEqual(['Point A', 'Point B']);
    expect(document.body.classList).toContain('modal-open');
  });

  it('n\'affiche le bouton .zip que si le projet l\'autorise', () => {
    open({ id: 2, zipUrl: '/downloads/mon-projet.zip' });
    expect(element.querySelector('a[download]')?.getAttribute('href')).toBe('/downloads/mon-projet.zip');
  });

  it('sans détail, reprend la carte sans bouton .zip ni aperçus', () => {
    open(null);

    expect(element.querySelector('a[download]')).toBeNull();
    expect(element.querySelector('.gallery')).toBeNull();
    expect(element.querySelector('.readme p')?.textContent).toBe('Description courte');
    // La description courte n'est pas répétée dans « À propos »
    expect(element.querySelector('.about p')).toBeNull();
  });

  it('fait défiler les aperçus avec les flèches et les miniatures', () => {
    open({
      id: 2,
      images: [
        { url: '/a.jpg', alt: 'A', caption: 'Écran A' },
        { url: '/b.jpg', alt: 'B' },
      ],
    });
    const current = () => element.querySelector('.stage img')?.getAttribute('src');

    expect(current()).toBe('/a.jpg');
    expect(element.querySelector('figcaption')?.textContent).toBe('Écran A');

    (element.querySelector('.nav.next') as HTMLElement).click();
    fixture.detectChanges();
    expect(current()).toBe('/b.jpg');

    (element.querySelector('.nav.next') as HTMLElement).click(); // revient au début
    fixture.detectChanges();
    expect(current()).toBe('/a.jpg');

    (element.querySelectorAll('.thumbnails button')[1] as HTMLElement).click();
    fixture.detectChanges();
    expect(current()).toBe('/b.jpg');
  });

  it('se ferme avec Échap, le bouton ou un clic à côté, et libère le défilement de la page', () => {
    open(null);
    const closed = spyOn(fixture.componentInstance.closed, 'emit');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    (element.querySelector('button[aria-label="Fermer"]') as HTMLElement).click();
    (element.querySelector('.backdrop') as HTMLElement).click();
    expect(closed).toHaveBeenCalledTimes(3);

    fixture.destroy();
    expect(document.body.classList).not.toContain('modal-open');
  });
});

describe('parseDescription', () => {
  it('sépare paragraphes et listes', () => {
    expect(parseDescription('Ligne 1\nsuite\n\n- a\n- b\n\n\nFin')).toEqual([
      { type: 'paragraph', text: 'Ligne 1 suite' },
      { type: 'list', items: ['a', 'b'] },
      { type: 'paragraph', text: 'Fin' },
    ]);
  });
});
