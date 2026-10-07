using System.Net;
using System.Text.RegularExpressions;
using MailKit.Net.Smtp;
using MailKit.Security;
using MimeKit;
using Portfolio.Api.Models;

namespace Portfolio.Api.Services
{
    public interface IContactMailer
    {
        Task SendAsync(SendEmailRequest request);
    }

    public class SmtpContactMailer(IConfiguration configuration) : IContactMailer
    {
        private const string SmtpHost = "mail.rotilio.fr";
        private const int SmtpPort = 587;
        private const string MailFrom = "noreply@rotilio.fr";
        private const string MailTo = "jules@rotilio.fr";

        public async Task SendAsync(SendEmailRequest request)
        {
            // Identifiants SMTP fournis par le fichier .env (SMTP_U / SMTP_P)
            var smtpUser = configuration["SMTP_U"];
            var smtpPassword = configuration["SMTP_P"];
            if (string.IsNullOrEmpty(smtpUser) || string.IsNullOrEmpty(smtpPassword))
            {
                throw new InvalidOperationException("SMTP_U ou SMTP_P n'est pas défini.");
            }

            var message = new MimeMessage();
            message.From.Add(MailboxAddress.Parse(MailFrom));
            message.To.Add(MailboxAddress.Parse(MailTo));
            // Permet de répondre directement au visiteur (l'adresse est aussi dans le corps du mail)
            if (MailboxAddress.TryParse(request.From, out var visitor))
            {
                message.ReplyTo.Add(visitor);
            }
            message.Subject = request.Subject;
            message.Body = new BodyBuilder { HtmlBody = BuildHtmlBody(request) }.ToMessageBody();

            using var smtpClient = new SmtpClient();
            await smtpClient.ConnectAsync(SmtpHost, SmtpPort, SecureSocketOptions.StartTls);
            // Contrairement à System.Net.Mail, un échec d'authentification lève une AuthenticationException
            await smtpClient.AuthenticateAsync(smtpUser, smtpPassword);
            await smtpClient.SendAsync(message);
            await smtpClient.DisconnectAsync(true);
        }

        // Tout ce qui vient du visiteur est encodé avant d'être inséré dans le HTML
        public static string BuildHtmlBody(SendEmailRequest request)
        {
            string from = WebUtility.HtmlEncode(request.From);
            string bodyHtml = Regex.Replace(WebUtility.HtmlEncode(request.Body), @"\r?\n", "<br />");
            return $"<p>De : {from}</p>" +
$@"
<p>Message : 
<br />
----------
<br />
{bodyHtml}
<br />
----------
</p>";
        }
    }
}
