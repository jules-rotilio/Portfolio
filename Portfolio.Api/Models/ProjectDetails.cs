namespace Portfolio.Api.Models
{
    /// <summary>Détail d'un projet renvoyé par GET /api/projects/{id} (voir docs/api-project-details.md).</summary>
    public class ProjectDetails
    {
        public required int ID { get; set; }
        public required string Name { get; set; }
        public required string Description { get; set; }
        public required string[] Technologies { get; set; }
        public required string LongDescription { get; set; }
        public required ProjectImage[] Images { get; set; }
        public required ProjectFileNode[] Files { get; set; }
        public string? ZipUrl { get; set; }
        public string? RepoUrl { get; set; }
    }

    public class ProjectImage
    {
        public required string Url { get; set; }
        public required string Alt { get; set; }
        public string? Caption { get; set; }
    }

    public class ProjectFileNode
    {
        public required string Name { get; set; }
        public required string Path { get; set; }
        public required string Type { get; set; }
        public long? Size { get; set; }
        public string? Content { get; set; }
        public string? Url { get; set; }
        public List<ProjectFileNode>? Children { get; set; }
    }

    /// <summary>
    /// Fichier project.json d'un dossier de contenu : ce qui ne se déduit pas des fichiers eux-mêmes.
    /// Les images y sont référencées par leur nom dans le dossier images/.
    /// </summary>
    public class ProjectContentManifest
    {
        public string? LongDescription { get; set; }
        public ProjectContentImage[] Images { get; set; } = [];
        /// <summary>Le .zip n'est proposé que si ce champ vaut explicitement true.</summary>
        public bool AllowZipDownload { get; set; }
        public string? RepoUrl { get; set; }
    }

    public class ProjectContentImage
    {
        public required string File { get; set; }
        public required string Alt { get; set; }
        public string? Caption { get; set; }
    }
}
