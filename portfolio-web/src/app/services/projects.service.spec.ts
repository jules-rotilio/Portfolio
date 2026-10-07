import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ProjectsService } from './projects.service';
import { ProjectDetails } from '../models/project';

describe('ProjectsService', () => {
  let service: ProjectsService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProjectsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('récupère les projets depuis l\'API', () => {
    let result: unknown;
    service.getProjects().subscribe((data) => (result = data));

    const req = http.expectOne('https://api.julesrotilio.fr/api/projects');
    expect(req.request.method).toBe('GET');
    req.flush([{ id: 0, name: 'Projet' }]);

    expect(result).toEqual([{ id: 0, name: 'Projet' }]);
  });
});

describe('ProjectsService : détail d\'un projet', () => {
  const card = { id: 3, name: 'Projet', description: 'Courte', technologies: ['C#'] };
  let service: ProjectsService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProjectsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('complète les informations de la carte avec le détail reçu', () => {
    let result: ProjectDetails | undefined;
    service.getProjectDetails(card).subscribe((d) => (result = d));

    http.expectOne('/mock/projects/3.json').flush({ id: 3, longDescription: 'Longue', zipUrl: '/p.zip' });

    expect(result?.name).toBe('Projet');
    expect(result?.description).toBe('Courte');
    expect(result?.longDescription).toBe('Longue');
    expect(result?.zipUrl).toBe('/p.zip');
    expect(result?.files).toEqual([]);
  });

  it('reprend la carte si le détail n\'est pas disponible', () => {
    let result: ProjectDetails | undefined;
    service.getProjectDetails(card).subscribe((d) => (result = d));

    http.expectOne('/mock/projects/3.json').flush('', { status: 404, statusText: 'Not Found' });

    expect(result).toEqual(ProjectsService.fromProject(card));
    expect(result?.longDescription).toBe('Courte');
    expect(result?.zipUrl).toBeNull();
  });
});
