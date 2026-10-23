import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FileBrowserComponent } from './file-browser.component';
import { ProjectFileNode } from '../../models/project';

const FILES: ProjectFileNode[] = [
  { name: 'README.md', path: 'README.md', type: 'file', size: 12, content: '# Titre\nTexte\n' },
  {
    name: 'src', path: 'src', type: 'directory', children: [
      { name: 'main.ts', path: 'src/main.ts', type: 'file', size: 30, content: 'console.log(1);\nconsole.log(2);' },
      { name: 'logo.png', path: 'src/logo.png', type: 'file', size: 2048, url: '/logo.png' },
      { name: 'data.bin', path: 'src/data.bin', type: 'file', size: 10 },
    ],
  },
];

describe('FileBrowserComponent', () => {
  let fixture: ComponentFixture<FileBrowserComponent>;
  let element: HTMLElement;

  function render(files: ProjectFileNode[]) {
    fixture.componentRef.setInput('files', files);
    fixture.detectChanges();
  }

  function names(): string[] {
    return Array.from(element.querySelectorAll('.tree .name')).map((n) => n.textContent!.trim());
  }

  function click(name: string) {
    const button = Array.from(element.querySelectorAll<HTMLButtonElement>('.tree .node')).find((b) => b.textContent!.trim() === name);
    button!.click();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [FileBrowserComponent] }).compileComponents();
    fixture = TestBed.createComponent(FileBrowserComponent);
    element = fixture.nativeElement;
  });

  it('affiche les dossiers en premier et ouvre le README rendu par défaut', () => {
    render(FILES);

    expect(names()).toEqual(['src', 'README.md']);
    expect(element.querySelector('.viewer-header strong')?.textContent).toBe('README.md');
    expect(element.querySelector('.markdown-body h1')?.textContent).toBe('Titre');
    expect(element.querySelector('.code')).toBeNull();
  });

  it('bascule un fichier Markdown entre l\'aperçu et le code source', () => {
    render(FILES);
    const [preview, source] = Array.from(element.querySelectorAll<HTMLButtonElement>('.view-toggle button'));

    source.click();
    fixture.detectChanges();
    expect(element.querySelector('.markdown-body')).toBeNull();
    expect(Array.from(element.querySelectorAll('.line pre')).map((l) => l.textContent)).toEqual(['# Titre', 'Texte']);

    preview.click();
    fixture.detectChanges();
    expect(element.querySelector('.markdown-body h1')).not.toBeNull();
  });

  it('colore le code selon l\'extension, y compris les blocs sur plusieurs lignes', () => {
    render([{ name: 'Program.cs', path: 'Program.cs', type: 'file', size: 40, content: '/* a\nb */\npublic class A { }\n' }]);
    click('Program.cs');

    const lines = Array.from(element.querySelectorAll('.line pre'));
    expect(lines.map((l) => l.textContent)).toEqual(['/* a', 'b */', 'public class A { }']);
    expect(lines[1].querySelector('.hljs-comment')?.textContent).toBe('b */');
    expect(lines[2].querySelector('.hljs-keyword')?.textContent).toBe('public');
  });

  it('échappe le contenu des fichiers sans langage connu', () => {
    render([{ name: 'notes.txt', path: 'notes.txt', type: 'file', size: 20, content: '<script>x</script>' }]);
    click('notes.txt');

    expect(element.querySelector('.line pre script')).toBeNull();
    expect(element.querySelector('.line pre')?.textContent).toBe('<script>x</script>');
  });

  it('déplie un dossier et affiche le fichier choisi avec ses numéros de ligne', () => {
    render(FILES);
    click('src');
    expect(names()).toEqual(['src', 'data.bin', 'logo.png', 'main.ts', 'README.md']);

    click('main.ts');
    expect(element.querySelector('.breadcrumb-path')?.textContent?.replace(/\s/g, '')).toBe('src/main.ts');
    expect(Array.from(element.querySelectorAll('.line-number')).map((n) => n.textContent)).toEqual(['1', '2']);

    click('src');
    expect(names()).toEqual(['src', 'README.md']);
  });

  it('affiche les images et signale les fichiers sans aperçu', () => {
    render(FILES);
    click('src');

    click('logo.png');
    expect(element.querySelector('.image-preview img')?.getAttribute('src')).toBe('/logo.png');

    click('data.bin');
    expect(element.querySelector('.viewer .empty')?.textContent).toContain('Aperçu non disponible');
  });

  it('indique quand le code n\'est pas partagé (arborescence seule)', () => {
    render([{ name: 'Program.cs', path: 'Program.cs', type: 'file', size: 120 }]);

    expect(names()).toEqual(['Program.cs']);
    expect(element.querySelector('.viewer .empty')?.textContent).toContain('pas partagé');
    click('Program.cs');
    expect(element.querySelector('.viewer .empty')?.textContent).toContain('pas partagé');
  });

  it('indique quand le projet n\'a pas encore de fichiers', () => {
    render([]);

    expect(element.querySelector('.tree')).toBeNull();
    expect(element.querySelector('.no-files')?.textContent).toContain('pas encore disponibles');
  });
});
