using System.Net;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.HttpOverrides;
using Portfolio.Api.Services;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddControllers();

builder.Services.AddSingleton<IContactMailer, SmtpContactMailer>();

// Contenu détaillé des projets (fichiers sources, aperçus), lu depuis ProjectContent:Path
builder.Services.AddSingleton<ProjectContentStore>();

// Learn more about configuring OpenAPI at https://aka.ms/aspnet/openapi
builder.Services.AddOpenApi();

builder.Services.AddCors(options =>
{
    options.AddPolicy(
        "AllowAngular",
        policy => policy.WithOrigins("https://julesrotilio.fr").AllowAnyHeader().AllowAnyMethod()
    );
});

// L'API est derrière nginx : on ne fait confiance à X-Forwarded-For que s'il vient du conteneur nginx,
// sinon n'importe qui pourrait choisir son IP et contourner la limite d'envoi.
builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    options.KnownIPNetworks.Clear();
    options.KnownProxies.Clear();
    options.KnownProxies.Add(IPAddress.Parse(builder.Configuration["TRUSTED_PROXY"] ?? "172.28.0.2"));
});

// Formulaire de contact : 5 messages par heure et par adresse IP
builder.Services.AddRateLimiter(options =>
{
    options.AddPolicy(
        "contact",
        context => RateLimitPartition.GetFixedWindowLimiter(
            context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            _ => new FixedWindowRateLimiterOptions { PermitLimit = 5, Window = TimeSpan.FromHours(1) }
        )
    );
    options.OnRejected = async (context, cancellationToken) =>
    {
        context.HttpContext.Response.StatusCode = StatusCodes.Status429TooManyRequests;
        await context.HttpContext.Response.WriteAsJsonAsync(
            new { success = false, message = "Trop de messages envoyés. Réessayez dans une heure." },
            cancellationToken
        );
    };
});

var app = builder.Build();

app.UseForwardedHeaders();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseCors("AllowAngular");

app.UseRateLimiter();

app.UseHttpsRedirection();

app.UseAuthorization();

app.MapControllers();

app.Run();

// Rend Program visible pour les tests d'intégration (WebApplicationFactory)
public partial class Program;
