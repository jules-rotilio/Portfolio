import { ComponentFixture, DeferBlockState, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { ProjetsComponent } from './projets.component';

const API_URL = 'https://api.julesrotilio.fr/api/projects';

function project(id: number, technologies: string[] = ['C#']) {
  return { id, name: `Projet ${id}`, description: `Description ${id}`, technologies };
}

describe('ProjetsComponent', () => {
  let fixture: ComponentFixture<ProjetsComponent>;
  let http: HttpTestingController;
  let element: HTMLElement;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProjetsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    // Écran d'ordinateur par défaut, quelle que soit la taille de la fenêtre de test
    spyOn(window, 'matchMedia').and.returnValue({ matches: false } as MediaQueryList);
    fixture = TestBed.createComponent(ProjetsComponent);
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    element = fixture.nativeElement;
    fixture.detectChanges(); // ngOnInit -> requête HTTP
  });

  afterEach(() => http.verify());

  it('affiche une tuile par projet, avec ses technologies', () => {
    http.expectOne(API_URL).flush([project(0, ['C#', '.NET 10', 'Angular']), project(1)]);
    fixture.detectChanges();

    const titles = Array.from(element.querySelectorAll('.project-title')).map((t) => t.textContent?.trim());
    expect(titles).toEqual(['Projet 0', 'Projet 1']);

    const chips = Array.from(element.querySelectorAll('.project')[0].querySelectorAll('.chips li')).map((c) => c.textContent?.trim());
    expect(chips).toEqual(['C#', '.NET 10', 'Angular']);
  });

  it('n\'affiche aucune tuile si l\'API est en erreur', () => {
    spyOn(console, 'error'); // l'erreur est journalisée, on évite le bruit dans la sortie des tests
    http.expectOne(API_URL).flush('KO', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(element.querySelectorAll('.project').length).toBe(0);
  });

  // ---------- Fenêtre de détail ----------

  // La fenêtre est chargée à la demande (@defer) : on attend la fin de la navigation et du chargement
  async function settle() {
    await fixture.whenStable();
    fixture.detectChanges();
    for (const block of await fixture.getDeferBlocks()) {
      await block.render(DeferBlockState.Complete);
    }
    fixture.detectChanges();
  }

  it('ouvre la fenêtre du projet indiqué par ?projet=ID, même si l\'URL arrive avant la liste', async () => {
    await router.navigateByUrl('/?projet=1');
    http.expectOne(API_URL).flush([project(0), project(1)]);
    await settle();

    // Ni contenu côté API ni données fictives : la fenêtre reprend les informations de la carte
    http.expectOne(`${API_URL}/1`).flush('', { status: 404, statusText: 'Not Found' });
    http.expectOne('/mock/projects/1.json').flush('', { status: 404, statusText: 'Not Found' });
    await settle();

    const dialog = element.querySelector('app-project-details [role="dialog"]');
    expect(dialog?.querySelector('h2')?.textContent).toContain('Projet 1');
    expect(dialog?.querySelector('.readme')?.textContent).toContain('Description 1');
  });

  it('cliquer sur une carte ajoute ?projet=ID à l\'URL, fermer le retire', async () => {
    http.expectOne(API_URL).flush([project(0), project(4)]);
    fixture.detectChanges();

    (element.querySelectorAll('.project-title a')[1] as HTMLElement).click();
    await settle();
    expect(router.url).toBe('/?projet=4');
    http.expectOne(`${API_URL}/4`).flush('', { status: 404, statusText: 'Not Found' });
    http.expectOne('/mock/projects/4.json').flush('', { status: 404, statusText: 'Not Found' });
    await settle();

    (element.querySelector('app-project-details button[aria-label="Fermer"]') as HTMLElement).click();
    await settle();
    expect(router.url).toBe('/');
    expect(element.querySelector('app-project-details')).toBeNull();
  });

  it('sur téléphone, affiche un petit message au lieu de la fiche détaillée', async () => {
    (window.matchMedia as jasmine.Spy).and.returnValue({ matches: true } as MediaQueryList);
    fixture.componentInstance.updateIsMobile();
    http.expectOne(API_URL).flush([project(0), project(4)]);
    fixture.detectChanges();

    (element.querySelectorAll('.project-title a')[1] as HTMLElement).click();
    await settle();
    expect(router.url).toBe('/?projet=4');
    expect(element.querySelector('app-project-details')).toBeNull();
    expect(element.querySelector('.mobile-notice h2')?.textContent).toContain('Projet 4');
    expect(element.querySelector('.mobile-notice p')?.textContent).toContain('ordinateur');

    (element.querySelector('.mobile-notice button') as HTMLElement).click();
    await settle();
    expect(router.url).toBe('/');
    expect(element.querySelector('.mobile-notice')).toBeNull();
  });

  it('n\'ouvre rien pour un ID inconnu', async () => {
    await router.navigateByUrl('/?projet=99');
    http.expectOne(API_URL).flush([project(0)]);
    await settle();

    expect(element.querySelector('app-project-details')).toBeNull();
  });
});
