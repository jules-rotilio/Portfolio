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

    fixture = TestBed.createComponent(ProjetsComponent);
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    element = fixture.nativeElement;
    fixture.detectChanges(); // ngOnInit -> requête HTTP
  });

  afterEach(() => http.verify());

  it('affiche une carte par projet, avec ses technologies', () => {
    http.expectOne(API_URL).flush([project(0, ['C#', '.NET 10', 'Angular']), project(1)]);
    fixture.detectChanges();

    const titles = Array.from(element.querySelectorAll('.card-title')).map((t) => t.textContent?.trim());
    expect(titles).toEqual(['Projet 0', 'Projet 1']);

    const badges = Array.from(element.querySelectorAll('.card')[0].querySelectorAll('.badge')).map((b) => b.textContent?.trim());
    expect(badges).toEqual(['C#', '.NET 10', 'Angular']);
  });

  it('range les projets par lignes de deux (dernière ligne incomplète)', () => {
    http.expectOne(API_URL).flush([project(0), project(1), project(2)]);
    fixture.detectChanges();

    const rows = element.querySelectorAll('.row');
    expect(rows.length).toBe(2);
    expect(rows[0].querySelectorAll('.card').length).toBe(2);
    expect(rows[1].querySelectorAll('.card').length).toBe(1);
  });

  it('n\'affiche aucune carte si l\'API est en erreur', () => {
    spyOn(console, 'error'); // l'erreur est journalisée, on évite le bruit dans la sortie des tests
    http.expectOne(API_URL).flush('KO', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(element.querySelectorAll('.card').length).toBe(0);
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

    // Pas encore de détail côté API : la fenêtre reprend les informations de la carte
    http.expectOne('/mock/projects/1.json').flush('', { status: 404, statusText: 'Not Found' });
    await settle();

    const dialog = element.querySelector('app-project-details [role="dialog"]');
    expect(dialog?.querySelector('h2')?.textContent).toContain('Projet 1');
    expect(dialog?.querySelector('.readme')?.textContent).toContain('Description 1');
  });

  it('cliquer sur une carte ajoute ?projet=ID à l\'URL, fermer le retire', async () => {
    http.expectOne(API_URL).flush([project(0), project(4)]);
    fixture.detectChanges();

    (element.querySelectorAll('.card-title a')[1] as HTMLElement).click();
    await settle();
    expect(router.url).toBe('/?projet=4');
    http.expectOne('/mock/projects/4.json').flush('', { status: 404, statusText: 'Not Found' });
    await settle();

    (element.querySelector('app-project-details button[aria-label="Fermer"]') as HTMLElement).click();
    await settle();
    expect(router.url).toBe('/');
    expect(element.querySelector('app-project-details')).toBeNull();
  });

  it('n\'ouvre rien pour un ID inconnu', async () => {
    await router.navigateByUrl('/?projet=99');
    http.expectOne(API_URL).flush([project(0)]);
    await settle();

    expect(element.querySelector('app-project-details')).toBeNull();
  });
});
