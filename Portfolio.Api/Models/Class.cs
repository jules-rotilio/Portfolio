using System.ComponentModel.DataAnnotations;

namespace Portfolio.Api.Models
{
    public class Project
    {
        public required int ID { get; set; }
        public required string Name { get; set; }
        public required string Description { get; set; }
        public required string[] Technologies { get; set; }
    }

    public class SendEmailRequest
    {
        [EmailAddress, StringLength(254)]
        public required string From { get; set; }

        // Pas de caractères de contrôle (retours à la ligne, tabulations...) dans le sujet
        [StringLength(150, MinimumLength = 1), RegularExpression(@"^[^\p{Cc}]*$")]
        public required string Subject { get; set; }

        [StringLength(5000, MinimumLength = 1)]
        public required string Body { get; set; }
    }
}
