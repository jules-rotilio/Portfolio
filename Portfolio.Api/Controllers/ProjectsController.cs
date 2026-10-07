using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.StaticFiles;
using Portfolio.Api.Models;
using Portfolio.Api.Services;

namespace Portfolio.Api.Controllers
{
    [ApiController]
    [Route("api")]
    public class ApiController(IContactMailer mailer, ProjectContentStore content, ILogger<ApiController> logger) : ControllerBase
    {
        // Seules les images sont affichées telles quelles ; tout autre fichier est proposé en téléchargement
        private static readonly string[] InlineExtensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"];
        private static readonly FileExtensionContentTypeProvider ContentTypes = new();

        [HttpGet("projects")]
        public IActionResult GetProjects()
        {
            var projects = ReadProjects();
            return projects is null ? NotFound("Projects.json not found.") : Ok(projects);
        }

        /// <summary>Détail d'un projet : 404 si le projet n'existe pas ou n'a pas encore de contenu détaillé.</summary>
        [HttpGet("projects/{id:int}")]
        public IActionResult GetProjectDetails(int id)
        {
            var project = ReadProjects()?.FirstOrDefault(p => p.ID == id);
            var details = project is null ? null : content.GetDetails(project);
            return details is null ? NotFound() : Ok(details);
        }

        [HttpGet("projects/{id:int}/files/{**path}")]
        public IActionResult GetProjectFile(int id, string path) => ServeFile(id, "files", path);

        [HttpGet("projects/{id:int}/images/{**path}")]
        public IActionResult GetProjectImage(int id, string path) => ServeFile(id, "images", path);

        [HttpGet("projects/{id:int}/zip")]
        public async Task<IActionResult> GetProjectZip(int id)
        {
            var project = ReadProjects()?.FirstOrDefault(p => p.ID == id);
            var zip = project is null ? null : await content.CreateZipAsync(id);
            return zip is null ? NotFound() : File(zip, "application/zip", $"{FileNameOf(project!.Name)}.zip");
        }

        private IActionResult ServeFile(int id, string area, string path)
        {
            var fullPath = content.GetFilePath(id, area, path);
            if (fullPath is null)
            {
                return NotFound();
            }

            // Un fichier ouvert directement ne peut exécuter aucun script (cas des SVG)
            Response.Headers.ContentSecurityPolicy = "default-src 'none'; style-src 'unsafe-inline'; sandbox";
            var extension = Path.GetExtension(fullPath).ToLowerInvariant();
            if (InlineExtensions.Contains(extension) && ContentTypes.TryGetContentType(fullPath, out var contentType))
            {
                return PhysicalFile(fullPath, contentType);
            }
            return PhysicalFile(fullPath, "application/octet-stream", Path.GetFileName(fullPath));
        }

        private static string FileNameOf(string name) =>
            string.Concat(name.Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' or '.' ? c : '-')).Trim('-');

        private static Project[]? ReadProjects()
        {
            // Chemin absolu vers le fichier Projects.json
            var jsonPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Projects.json");
            return System.IO.File.Exists(jsonPath)
                ? JsonSerializer.Deserialize<Project[]>(System.IO.File.ReadAllText(jsonPath))
                : null;
        }

        [HttpPost("send-email")]
        [EnableRateLimiting("contact")]
        public async Task<IActionResult> SendEmail([FromBody] SendEmailRequest request)
        {
            try
            {
                await mailer.SendAsync(request);
                return Ok(new { success = true, message = "Email envoyé." });
            }
            catch (Exception ex)
            {
                // Le détail reste dans les logs, le visiteur reçoit un message simple
                logger.LogError(ex, "Échec de l'envoi du mail de contact.");
                return StatusCode(500, new { success = false, message = "Une erreur est survenue lors de l'envoi. Réessayez plus tard." });
            }
        }
    }
}
