using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Portfolio.Api.Models;
using Portfolio.Api.Services;

namespace Portfolio.Api.Controllers
{
    [ApiController]
    [Route("api")]
    public class ApiController(IContactMailer mailer, ILogger<ApiController> logger) : ControllerBase
    {
        [HttpGet("projects")]
        public IActionResult GetProjects()
        {
            // Chemin absolu vers le fichier Projects.json
            var jsonPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Projects.json");
            if (!System.IO.File.Exists(jsonPath))
            {
                return NotFound("Projects.json not found.");
            }

            var json = System.IO.File.ReadAllText(jsonPath);
            var projects = JsonSerializer.Deserialize<Project[]>(json);

            return Ok(projects);
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
