import { Component, Input } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { ProjectFileNode } from '../../models/project';

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
  expanded = new Set<string>();
  selected: ProjectFileNode | null = null;

  @Input() set files(files: ProjectFileNode[]) {
    this.tree = sortNodes(files ?? []);
    this.expanded.clear();
    // Comme sur GitHub, le README racine est ouvert par défaut
    this.selected = this.tree.find((n) => n.type === 'file' && !!n.content && /^readme(\.|$)/i.test(n.name)) ?? null;
  }

  toggle(node: ProjectFileNode): void {
    if (node.type === 'directory') {
      if (this.expanded.has(node.path)) {
        this.expanded.delete(node.path);
      } else {
        this.expanded.add(node.path);
      }
    } else {
      this.selected = node;
    }
  }

  get breadcrumb(): string[] {
    return this.selected ? this.selected.path.split('/') : [];
  }

  get lines(): string[] {
    return this.selected?.content?.replace(/\n$/, '').split('\n') ?? [];
  }

  isImage(node: ProjectFileNode): boolean {
    return !!node.url && IMAGE_EXTENSIONS.includes(extension(node.name));
  }

  icon(node: ProjectFileNode): string {
    if (node.type === 'directory') {
      return this.expanded.has(node.path) ? 'bi-folder2-open' : 'bi-folder-fill';
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
