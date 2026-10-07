using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Portfolio.Api.Models;
using Portfolio.Api.Services;

namespace Portfolio.Api.Tests
{
    /// <summary>Remplace l'envoi SMTP : enregistre les demandes, ou échoue si demandé.</summary>
    public class FakeMailer : IContactMailer
    {
        public List<SendEmailRequest> Sent { get; } = [];
        public bool Fail { get; set; }

        public Task SendAsync(SendEmailRequest request)
        {
            if (Fail) throw new InvalidOperationException("détail interne SMTP");
            Sent.Add(request);
            return Task.CompletedTask;
        }
    }

    /// <summary>
    /// Le serveur de test n'a pas d'IP client (null), ce qui n'arrive jamais avec Kestrel en production.
    /// On simule un visiteur extérieur pour que la vérification X-Forwarded-For se comporte comme en vrai.
    /// </summary>
    public class FakeRemoteIpStartupFilter : IStartupFilter
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
        {
            app.Use((context, nextMiddleware) =>
            {
                context.Connection.RemoteIpAddress = IPAddress.Parse("198.51.100.7");
                return nextMiddleware(context);
            });
            next(app);
        };
    }

    // Chaque test crée sa propre application : le compteur de la limite d'envoi repart de zéro.
    public class ApiTests : IDisposable
    {
        private readonly FakeMailer _mailer = new();
        private readonly WebApplicationFactory<Program> _factory;
        private readonly HttpClient _client;

        public ApiTests()
        {
            _factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
                builder.ConfigureServices(services =>
                {
                    services.RemoveAll<IContactMailer>();
                    services.AddSingleton<IContactMailer>(_mailer);
                    services.AddSingleton<IStartupFilter, FakeRemoteIpStartupFilter>();
                }));
            _client = _factory.CreateClient();
        }

        public void Dispose()
        {
            _client.Dispose();
            _factory.Dispose();
        }

        private static object ValidMessage(string body = "Bonjour !") =>
            new { from = "visiteur@example.com", subject = "Prise de contact", body };

        private Task<HttpResponseMessage> PostEmail(object payload) =>
            _client.PostAsJsonAsync("/api/send-email", payload);

        private static async Task<string?> MessageOf(HttpResponseMessage response) =>
            (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("message").GetString();

        // ---------- /api/projects ----------

        [Fact]
        public async Task Projects_AreAllComplete_AndIdsAreUnique()
        {
            // Protège contre une erreur de saisie dans Projects.json (champ manquant, ID en double...)
            var projects = await _client.GetFromJsonAsync<JsonElement[]>("/api/projects");

            Assert.NotNull(projects);
            Assert.NotEmpty(projects);
            foreach (var p in projects)
            {
                Assert.False(string.IsNullOrWhiteSpace(p.GetProperty("name").GetString()));
                Assert.False(string.IsNullOrWhiteSpace(p.GetProperty("description").GetString()));
                Assert.NotEqual(0, p.GetProperty("technologies").GetArrayLength());
            }
            var ids = projects.Select(p => p.GetProperty("id").GetInt32()).ToList();
            Assert.Equal(ids.Count, ids.Distinct().Count());
        }

        // ---------- /api/send-email : validation ----------

        [Fact]
        public async Task SendEmail_ValidMessage_IsSent()
        {
            var response = await PostEmail(ValidMessage());

            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var sent = Assert.Single(_mailer.Sent);
            Assert.Equal("visiteur@example.com", sent.From);
            Assert.Equal("Prise de contact", sent.Subject);
        }

        [Theory]
        [InlineData("pas-un-email", "Sujet", "Message")]           // adresse invalide
        [InlineData("a@b.fr", "Sujet\r\nBcc: x@y.z", "Message")]  // injection d'en-tête dans le sujet
        [InlineData("a@b.fr", "", "Message")]                     // sujet vide
        [InlineData("a@b.fr", "Sujet", "")]                       // message vide
        public async Task SendEmail_InvalidInput_IsRejected_AndNothingIsSent(string from, string subject, string body)
        {
            var response = await PostEmail(new { from, subject, body });

            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Empty(_mailer.Sent);
        }

        [Fact]
        public async Task SendEmail_TooLongMessage_IsRejected()
        {
            var response = await PostEmail(ValidMessage(new string('a', 5001)));

            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Empty(_mailer.Sent);
        }

        // ---------- /api/send-email : erreurs et limite d'envoi ----------

        [Fact]
        public async Task SendEmail_MailerFailure_ReturnsSimpleMessage_WithoutInternalDetails()
        {
            _mailer.Fail = true;

            var response = await PostEmail(ValidMessage());

            Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
            var message = await MessageOf(response);
            Assert.Equal("Une erreur est survenue lors de l'envoi. Réessayez plus tard.", message);
            Assert.DoesNotContain("SMTP", await response.Content.ReadAsStringAsync());
        }

        [Fact]
        public async Task SendEmail_SixthMessageWithinAnHour_IsRateLimited()
        {
            for (int i = 0; i < 5; i++)
            {
                Assert.Equal(HttpStatusCode.OK, (await PostEmail(ValidMessage())).StatusCode);
            }

            var response = await PostEmail(ValidMessage());

            Assert.Equal(HttpStatusCode.TooManyRequests, response.StatusCode);
            Assert.Equal("Trop de messages envoyés. Réessayez dans une heure.", await MessageOf(response));
            Assert.Equal(5, _mailer.Sent.Count);
        }

        [Fact]
        public async Task SendEmail_FakeForwardedForHeader_DoesNotBypassRateLimit()
        {
            // Une IP différente dans X-Forwarded-For à chaque requête ne doit pas remettre le compteur à zéro :
            // seul le conteneur nginx (TRUSTED_PROXY) est autorisé à fournir ce header.
            HttpResponseMessage? last = null;
            for (int i = 1; i <= 6; i++)
            {
                var request = new HttpRequestMessage(HttpMethod.Post, "/api/send-email") { Content = JsonContent.Create(ValidMessage()) };
                request.Headers.Add("X-Forwarded-For", $"203.0.113.{i}");
                last = await _client.SendAsync(request);
            }

            Assert.Equal(HttpStatusCode.TooManyRequests, last!.StatusCode);
        }

        // ---------- CORS ----------

        [Theory]
        [InlineData("https://julesrotilio.fr", true)]
        [InlineData("https://julesrotilio.synology.me", false)]
        [InlineData("https://evil.example", false)]
        public async Task Cors_OnlyAllowsTheWebsiteOrigin(string origin, bool allowed)
        {
            var request = new HttpRequestMessage(HttpMethod.Options, "/api/send-email");
            request.Headers.Add("Origin", origin);
            request.Headers.Add("Access-Control-Request-Method", "POST");
            request.Headers.Add("Access-Control-Request-Headers", "content-type");

            var response = await _client.SendAsync(request);

            Assert.Equal(allowed, response.Headers.Contains("Access-Control-Allow-Origin"));
        }
    }

    public class ContactMailerTests
    {
        [Fact]
        public void BuildHtmlBody_EncodesVisitorInput()
        {
            var html = SmtpContactMailer.BuildHtmlBody(new SendEmailRequest
            {
                From = "a@b.fr",
                Subject = "Sujet",
                Body = "<script>alert(1)</script> <a href=\"https://phishing.example\">clic</a>"
            });

            Assert.DoesNotContain("<script>", html);
            Assert.DoesNotContain("<a href", html);
            Assert.Contains("&lt;script&gt;", html);
        }

        [Fact]
        public void BuildHtmlBody_KeepsLineBreaks()
        {
            var html = SmtpContactMailer.BuildHtmlBody(new SendEmailRequest { From = "a@b.fr", Subject = "S", Body = "ligne 1\r\nligne 2\nligne 3" });

            Assert.Contains("ligne 1<br />ligne 2<br />ligne 3", html);
        }

        [Fact]
        public async Task SendAsync_WithoutSmtpCredentials_FailsBeforeContactingTheServer()
        {
            var config = new Microsoft.Extensions.Configuration.ConfigurationBuilder().Build();
            var mailer = new SmtpContactMailer(config);

            await Assert.ThrowsAsync<InvalidOperationException>(() =>
                mailer.SendAsync(new SendEmailRequest { From = "a@b.fr", Subject = "S", Body = "B" }));
        }
    }
}
