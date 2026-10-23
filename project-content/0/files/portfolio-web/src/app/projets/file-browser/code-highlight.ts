import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import csharp from 'highlight.js/lib/languages/csharp';
import css from 'highlight.js/lib/languages/css';
import dockerfile from 'highlight.js/lib/languages/dockerfile';
import http from 'highlight.js/lib/languages/http';
import ini from 'highlight.js/lib/languages/ini';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import nginx from 'highlight.js/lib/languages/nginx';
import powershell from 'highlight.js/lib/languages/powershell';
import python from 'highlight.js/lib/languages/python';
import scss from 'highlight.js/lib/languages/scss';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';
import { Marked } from 'marked';

// Seuls les langages présents dans project-content sont chargés, pour garder un bundle léger
const LANGUAGES = { bash, csharp, css, dockerfile, http, ini, javascript, json, markdown, nginx, powershell, python, scss, typescript, xml, yaml };
for (const [name, language] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, language);
}
hljs.registerAliases(['cs', 'c#'], { languageName: 'csharp' });
hljs.registerAliases(['ps1', 'ps'], { languageName: 'powershell' });
hljs.registerAliases(['sh', 'shell', 'console'], { languageName: 'bash' });
hljs.registerAliases(['html', 'cshtml', 'razor', 'xaml', 'csproj'], { languageName: 'xml' });

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  cs: 'csharp', old: 'csharp',
  py: 'python',
  ts: 'typescript', js: 'javascript', json: 'json',
  css: 'css', scss: 'scss',
  html: 'xml', cshtml: 'xml', xml: 'xml', xaml: 'xml', svg: 'xml', resx: 'xml', csproj: 'xml', esproj: 'xml',
  pubxml: 'xml', plist: 'xml', manifest: 'xml', appxmanifest: 'xml', slnx: 'xml',
  ps1: 'powershell', psm1: 'powershell', psd1: 'powershell',
  sh: 'bash', yml: 'yaml', yaml: 'yaml', conf: 'nginx', http: 'http', editorconfig: 'ini',
  md: 'markdown'
};

/** Langage highlight.js d'un fichier, ou null pour l'afficher en texte brut. */
export function languageFor(fileName: string): string | null {
  if (/^dockerfile$/i.test(fileName)) return 'dockerfile';
  const dot = fileName.lastIndexOf('.');
  const ext = dot >= 0 ? fileName.slice(dot + 1).toLowerCase() : '';
  return LANGUAGE_BY_EXTENSION[ext] ?? null;
}

/**
 * Code coloré, découpé en lignes HTML (une par ligne du fichier, pour garder les numéros de ligne).
 * highlight.js échappe tout le texte : le HTML produit ne contient que ses propres <span>.
 */
export function highlightLines(content: string, language: string | null): string[] {
  const html = language ? hljs.highlight(content, { language, ignoreIllegals: true }).value : escapeHtml(content);
  return splitLines(html.replace(/\r\n?/g, '\n').replace(/\n$/, ''));
}

/** Les <span> ouverts sur plusieurs lignes (commentaires, chaînes) sont refermés en fin de ligne et rouverts au début de la suivante. */
function splitLines(html: string): string[] {
  const open: string[] = [];
  return html.split('\n').map((line) => {
    const prefix = open.join('');
    for (const [tag] of line.matchAll(/<span[^>]*>|<\/span>/g)) {
      if (tag === '</span>') open.pop();
      else open.push(tag);
    }
    return prefix + line + '</span>'.repeat(open.length);
  });
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const marked = new Marked({
  gfm: true,
  renderer: {
    // Blocs de code colorés comme les fichiers
    code({ text, lang }) {
      const language = lang && hljs.getLanguage(lang) ? lang : null;
      const body = language ? hljs.highlight(text, { language, ignoreIllegals: true }).value : escapeHtml(text);
      return `<pre><code class="hljs">${body}</code></pre>\n`;
    }
  }
});

/** Markdown rendu en HTML (à afficher via [innerHTML], qui le nettoie). */
export function renderMarkdown(content: string): string {
  return marked.parse(content, { async: false });
}
