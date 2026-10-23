import { Component, ElementRef, Input, ViewChild } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ProjectFileNode } from '../../models/project';
import { highlightLines, languageFor, renderMarkdown } from './code-highlight';

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico'];

/** Explorateur de fichiers façon GitHub : arborescence dépliable à gauche, contenu du fichier à droite. */
@Component({
  selector: 'app-file-browser',
  imports: [NgTemplateOutlet],
  templateUrl: './file-browser.component.html',
  styleUrl: './file-browser.component.scss'
})
export class FileBrowserComponent {
  tree: ProjectFileNode[] = [];
  expandedDirs = new Set<string>();
  /** Lignes colorées du fichier affiché (HTML produit par highlight.js, déjà échappé). */
  lines: SafeHtml[] = [];
  /** Rendu du fichier Markdown affiché, ou null pour les autres fichiers. */
  markdownHtml: string | null = null;
  /** Pour un fichier Markdown : vrai pour voir le source plutôt que le rendu, comme sur GitHub. */
  showSource = false;
  private _selected: ProjectFileNode | null = null;
  /** Vrai quand le code est affiché dans une grande fenêtre, au-dessus de la fiche du projet. */
  expanded = false;
  @ViewChild('expandButton') expandButton?: ElementRef<HTMLButtonElement>;
  /** Faux quand l'API ne partage que l'arborescence (projet sans .zip autorisé). */
  codeShared = true;

  constructor(private sanitizer: DomSanitizer) {}

  get selected(): ProjectFileNode | null {
    return this._selected;
  }

  set selected(node: ProjectFileNode | null) {
    this._selected = node;
    this.showSource = false;
    const content = node?.content;
    const language = node ? languageFor(node.name) : null;
    // Calculé une seule fois par fichier : la coloration est trop coûteuse pour un getter appelé à chaque détection
    this.lines = content ? highlightLines(content, language).map((line) => this.sanitizer.bypassSecurityTrustHtml(line)) : [];
    this.markdownHtml = content && language === 'markdown' ? renderMarkdown(content) : null;
  }

  @Input() set files(files: ProjectFileNode[]) {
    this.tree = sortNodes(files ?? []);
    this.expandedDirs.clear();
    this.expanded = false;
    this.codeShared = this.tree.length === 0 || hasReadableFile(this.tree);
    // Comme sur GitHub, le README racine est ouvert par défaut
    this.selected = this.tree.find((n) => n.type === 'file' && !!n.content && /^readme(\.|$)/i.test(n.name)) ?? null;
  }

  setExpanded(expanded: boolean): void {
    this.expanded = expanded;
    // Le bouton change de place avec la fenêtre : on lui rend le focus pour le clavier
    setTimeout(() => this.expandButton?.nativeElement.focus());
  }

  toggle(node: ProjectFileNode): void {
    if (node.type === 'directory') {
      if (this.expandedDirs.has(node.path)) {
        this.expandedDirs.delete(node.path);
      } else {
        this.expandedDirs.add(node.path);
      }
    } else {
      this.selected = node;
    }
  }

  get breadcrumb(): string[] {
    return this.selected ? this.selected.path.split('/') : [];
  }

  isImage(node: ProjectFileNode): boolean {
    return !!node.url && IMAGE_EXTENSIONS.includes(extension(node.name));
  }

  icon(node: ProjectFileNode): string {
    if (node.type === 'directory') {
      return this.expandedDirs.has(node.path) ? 'bi-folder2-open' : 'bi-folder-fill';
    }
    const ext = extension(node.name);
    if (IMAGE_EXTENSIONS.includes(ext)) return 'bi-file-earmark-image';
    if (ext === 'md') return 'bi-file-earmark-text';
    if (['json', 'yml', 'yaml', 'xml', 'csproj', 'sln', 'conf'].includes(ext)) return 'bi-file-earmark-code';
    return 'bi-file-earmark';
  }

  formatSize(bytes?: number): string {
    if (bytes == null) return '';
    if (bytes < 1024) return `${bytes} o`;
    return `${(bytes / 1024).toFixed(1).replace('.', ',')} Ko`;
  }
}

function hasReadableFile(nodes: ProjectFileNode[]): boolean {
  return nodes.some((n) => !!n.content || !!n.url || hasReadableFile(n.children ?? []));
}

function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}

/** Dossiers d'abord, puis ordre alphabétique, comme sur GitHub. */
function sortNodes(nodes: ProjectFileNode[]): ProjectFileNode[] {
  return [...nodes]
    .map((n) => (n.children ? { ...n, children: sortNodes(n.children) } : n))
    .sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'directory' ? -1 : 1));
}
