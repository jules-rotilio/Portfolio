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
  const API = 'https://api.julesrotilio.fr/api/projects';
  const card = { id: 3, name: 'Projet', description: 'Courte', technologies: ['C#'] };
  let service: ProjectsService;
  let http: HttpTestingController;
  let result: ProjectDetails | undefined;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProjectsService);
    http = TestBed.inject(HttpTestingController);
    result = undefined;
    service.getProjectDetails(card).subscribe((d) => (result = d));
  });

  afterEach(() => http.verify());

  const notFound = { status: 404, statusText: 'Not Found' };

  it('lit le détail depuis l\'API et complète ses URL relatives avec le domaine de l\'API', () => {
    http.expectOne(`${API}/3`).flush({
      id: 3,
      longDescription: 'Longue',
      zipUrl: '/api/projects/3/zip',
      images: [{ url: '/api/projects/3/images/a.png', alt: 'A' }],
      files: [{ name: 'src', path: 'src', type: 'directory', children: [
        { name: 'a.png', path: 'src/a.png', type: 'file', url: '/api/projects/3/files/src/a.png' },
      ] }],
    });

    expect(result?.name).toBe('Projet');
    expect(result?.longDescription).toBe('Longue');
    expect(result?.zipUrl).toBe('https://api.julesrotilio.fr/api/projects/3/zip');
    expect(result?.images[0].url).toBe('https://api.julesrotilio.fr/api/projects/3/images/a.png');
    expect(result?.files[0].children?.[0].url).toBe('https://api.julesrotilio.fr/api/projects/3/files/src/a.png');
  });

  it('se rabat sur les données fictives si l\'API n\'a pas de contenu pour ce projet', () => {
    http.expectOne(`${API}/3`).flush('', notFound);
    http.expectOne('/mock/projects/3.json').flush({ id: 3, longDescription: 'Fictive', zipUrl: '/p.zip' });

    expect(result?.description).toBe('Courte');
    expect(result?.longDescription).toBe('Fictive');
    expect(result?.zipUrl).toBe('/p.zip');
    expect(result?.files).toEqual([]);
  });

  it('reprend la carte si aucun détail n\'est disponible', () => {
    http.expectOne(`${API}/3`).flush('', notFound);
    http.expectOne('/mock/projects/3.json').flush('', notFound);

    expect(result).toEqual(ProjectsService.fromProject(card));
  });
});
