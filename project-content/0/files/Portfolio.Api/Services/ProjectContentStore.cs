using System.IO.Compression;
using System.Text;
using System.Text.Json;
using Portfolio.Api.Models;

namespace Portfolio.Api.Services
{
    /// <summary>
    /// Lit le contenu détaillé des projets depuis un dossier (ProjectContent:Path), un sous-dossier par ID :
    /// <code>
    /// {id}/project.json   description longue, images, autorisation du .zip
    /// {id}/files/         fichiers sources affichés dans l'arborescence (contenu lisible seulement si le .zip est autorisé)
    /// {id}/images/        aperçus de l'application
    /// </code>
    /// </summary>
    public class ProjectContentStore(IConfiguration configuration, IWebHostEnvironment environment)
    {
        /// <summary>Au-delà, le contenu n'est pas inclus dans la réponse : le fichier reste téléchargeable via son URL.</summary>
        public const int MaxInlineContentBytes = 64 * 1024;

        private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

        // Filet de sécurité : ces fichiers et dossiers ne sont jamais publiés, même s'ils ont été copiés par erreur
        private static readonly string[] IgnoredNames = [".git", ".venv", "venv", "env", "__pycache__", "node_modules", "bin", "obj", ".idea", ".vs", ".vscode", "site-packages"];

        public string RootPath { get; } = ResolveRoot(configuration, environment);

        private static string ResolveRoot(IConfiguration configuration, IWebHostEnvironment environment)
        {
            var path = configuration["ProjectContent:Path"] ?? "project-content";
            return Path.GetFullPath(Path.IsPathRooted(path) ? path : Path.Combine(environment.ContentRootPath, path));
        }

        private string ProjectDirectory(int id) => Path.Combine(RootPath, id.ToString());

        public bool HasContent(int id) => Directory.Exists(ProjectDirectory(id));

        public ProjectDetails? GetDetails(Project project)
        {
            var directory = ProjectDirectory(project.ID);
            if (!Directory.Exists(directory))
            {
                return null;
            }

            var manifest = ReadManifest(directory);
            var baseUrl = $"/api/projects/{project.ID}";
            var filesDirectory = Path.Combine(directory, "files");

            return new ProjectDetails
            {
                ID = project.ID,
                Name = project.Name,
                Description = project.Description,
                Technologies = project.Technologies,
                LongDescription = string.IsNullOrWhiteSpace(manifest.LongDescription) ? project.Description : manifest.LongDescription,
                Images = manifest.Images
                    .Where(i => GetFilePath(project.ID, "images", i.File) is not null)
                    .Select(i => new ProjectImage { Url = $"{baseUrl}/images/{Uri.EscapeDataString(i.File)}", Alt = i.Alt, Caption = i.Caption })
                    .ToArray(),
                Files = Directory.Exists(filesDirectory) ? ReadTree(new DirectoryInfo(filesDirectory), "", baseUrl, manifest.AllowZipDownload).ToArray() : [],
                ZipUrl = manifest.AllowZipDownload && Directory.Exists(filesDirectory) ? $"{baseUrl}/zip" : null,
                RepoUrl = manifest.RepoUrl,
            };
        }

        /// <summary>Chemin d'un fichier sous files/ ou images/, ou null s'il n'existe pas ou sort du dossier.</summary>
        public string? GetFilePath(int id, string area, string relativePath)
        {
            if (area is not ("files" or "images"))
            {
                return null;
            }
            // Sans .zip autorisé, le code n'est pas partagé : l'arborescence reste visible, pas le contenu des fichiers
            if (area == "files" && !ReadManifest(ProjectDirectory(id)).AllowZipDownload)
            {
                return null;
            }
            var root = Path.Combine(ProjectDirectory(id), area);
            var path = ResolveInside(root, relativePath);
            return path is not null && File.Exists(path) && !IsIgnored(relativePath) && !HasLinkBetween(root, path) ? path : null;
        }

        /// <summary>Archive .zip des fichiers sources, ou null si le projet ne l'autorise pas explicitement.</summary>
        public async Task<byte[]?> CreateZipAsync(int id)
        {
            var directory = ProjectDirectory(id);
            var filesDirectory = Path.Combine(directory, "files");
            if (!Directory.Exists(filesDirectory) || !ReadManifest(directory).AllowZipDownload)
            {
                return null;
            }

            using var buffer = new MemoryStream();
            using (var archive = new ZipArchive(buffer, ZipArchiveMode.Create, leaveOpen: true))
            {
                foreach (var file in EnumerateFiles(new DirectoryInfo(filesDirectory), ""))
                {
                    var entry = archive.CreateEntry(file.RelativePath, CompressionLevel.Optimal);
                    await using var entryStream = entry.Open();
                    await using var source = file.Info.OpenRead();
                    await source.CopyToAsync(entryStream);
                }
            }
            return buffer.ToArray();
        }

        private static ProjectContentManifest ReadManifest(string directory)
        {
            var path = Path.Combine(directory, "project.json");
            return File.Exists(path)
                ? JsonSerializer.Deserialize<ProjectContentManifest>(File.ReadAllText(path), JsonOptions) ?? new()
                : new();
        }

        private static IEnumerable<ProjectFileNode> ReadTree(DirectoryInfo directory, string prefix, string baseUrl, bool shareContent)
        {
            foreach (var child in VisibleDirectories(directory))
            {
                var path = prefix + child.Name;
                yield return new ProjectFileNode
                {
                    Name = child.Name,
                    Path = path,
                    Type = "directory",
                    Children = ReadTree(child, path + "/", baseUrl, shareContent).ToList(),
                };
            }
            foreach (var file in VisibleFiles(directory))
            {
                var path = prefix + file.Name;
                yield return new ProjectFileNode
                {
                    Name = file.Name,
                    Path = path,
                    Type = "file",
                    Size = file.Length,
                    Content = shareContent ? ReadText(file) : null,
                    Url = shareContent ? $"{baseUrl}/files/{string.Join('/', path.Split('/').Select(Uri.EscapeDataString))}" : null,
                };
            }
        }

        private static IEnumerable<(FileInfo Info, string RelativePath)> EnumerateFiles(DirectoryInfo directory, string prefix)
        {
            foreach (var file in VisibleFiles(directory))
            {
                yield return (file, prefix + file.Name);
            }
            foreach (var child in VisibleDirectories(directory))
            {
                foreach (var file in EnumerateFiles(child, prefix + child.Name + "/"))
                {
                    yield return file;
                }
            }
        }

        // Les liens symboliques sont ignorés : ils pourraient pointer hors du dossier de contenu
        private static IEnumerable<DirectoryInfo> VisibleDirectories(DirectoryInfo directory) =>
            directory.EnumerateDirectories()
                .Where(d => !d.Attributes.HasFlag(FileAttributes.ReparsePoint) && !IsIgnoredName(d.Name))
                .OrderBy(d => d.Name, StringComparer.OrdinalIgnoreCase);

        private static IEnumerable<FileInfo> VisibleFiles(DirectoryInfo directory) =>
            directory.EnumerateFiles()
                .Where(f => !f.Attributes.HasFlag(FileAttributes.ReparsePoint) && !IsIgnoredName(f.Name))
                .OrderBy(f => f.Name, StringComparer.OrdinalIgnoreCase);

        private static bool IsIgnoredName(string name) =>
            IgnoredNames.Contains(name, StringComparer.OrdinalIgnoreCase) || name.StartsWith(".env", StringComparison.OrdinalIgnoreCase);

        private static bool IsIgnored(string relativePath) =>
            relativePath.Split('/', '\\').Any(IsIgnoredName);

        /// <summary>Contenu texte (UTF-8) d'un fichier, ou null s'il est binaire ou trop volumineux.</summary>
        private static string? ReadText(FileInfo file)
        {
            if (file.Length > MaxInlineContentBytes)
            {
                return null;
            }
            var bytes = File.ReadAllBytes(file.FullName);
            if (Array.IndexOf(bytes, (byte)0) >= 0)
            {
                return null;
            }
            try
            {
                return new UTF8Encoding(false, throwOnInvalidBytes: true).GetString(bytes).TrimStart('﻿');
            }
            catch (DecoderFallbackException)
            {
                return null;
            }
        }

        /// <summary>Vrai si le fichier ou l'un de ses dossiers parents (sous <paramref name="root"/>) est un lien symbolique.</summary>
        private static bool HasLinkBetween(string root, string path)
        {
            var fullRoot = Path.GetFullPath(root);
            for (var current = path; current.Length > fullRoot.Length; current = Path.GetDirectoryName(current)!)
            {
                if (File.GetAttributes(current).HasFlag(FileAttributes.ReparsePoint))
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>Combine sans jamais sortir de <paramref name="root"/> (protection contre « ../ »).</summary>
        private static string? ResolveInside(string root, string relativePath)
        {
            var fullRoot = Path.GetFullPath(root) + Path.DirectorySeparatorChar;
            var full = Path.GetFullPath(Path.Combine(fullRoot, relativePath));
            return full.StartsWith(fullRoot, StringComparison.Ordinal) ? full : null;
        }
    }
}
