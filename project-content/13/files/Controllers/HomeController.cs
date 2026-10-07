using System.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using WebOllama.Models;
using System.Text.Json;
using System.Text;
using System.Net;

namespace WebOllama.Controllers;

public class HomeController : Controller
{
    private readonly IOllamaModelService _ollama;

    public HomeController(IOllamaModelService ollama)
    {
        _ollama = ollama;
    }

    public IActionResult Index()
    {
        _ollama.RefreshAsync().GetAwaiter().GetResult();
        var models = _ollama.Models;
        return View(models);
    }

    [HttpPost]
    public async Task<IActionResult> AskModel(
    string prompt,
    string model,
    string context,
    string caveman,
    string mode,          // "normal", "plan", "execute"
    string? planJson,     // utilisé seulement en mode execute
    List<IFormFile>? files,
    [FromServices] IHttpClientFactory httpClientFactory)
    {
        if (string.IsNullOrWhiteSpace(prompt))
            return BadRequest("Prompt cannot be empty.");

        var client = httpClientFactory.CreateClient("ollama");

        // Construire le prompt selon le mode
        var fullPrompt = BuildPrompt(
            prompt: prompt,
            context: context,
            mode: mode,
            planJson: planJson,
            files: files,
            caveman: caveman
        );

        var payload = new
        {
            model = model,
            prompt = fullPrompt,
            stream = false
        };

        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var sw = Stopwatch.StartNew();

        try
        {
            var response = await client.PostAsync("/api/generate", content);
            var responseString = await response.Content.ReadAsStringAsync();
            sw.Stop();

            using var doc = JsonDocument.Parse(responseString);

            if (response.IsSuccessStatusCode)
            {
                var answer = doc.RootElement.GetProperty("response").GetString();

                return Json(new
                {
                    answer,
                    durationMs = sw.ElapsedMilliseconds
                });
            }
            else
            {
                var detail = doc.RootElement.GetProperty("error").GetString();
                return Problem(detail: detail, statusCode: 500);
            }
        }
        catch (Exception ex)
        {
            return Problem(statusCode: 500, detail: ex.Message);
        }
    }


    private string BuildPrompt(
    string prompt,
    string context,
    string mode,
    string caveman,
    string? planJson,
    List<IFormFile>? files)
{
    var sb = new StringBuilder();

    if (!string.IsNullOrWhiteSpace(context))
        sb.AppendLine(context);

    if (mode == "plan")
    {
        sb.AppendLine("You are a planning assistant.");
        sb.AppendLine("Analyze the user's request and produce a clear, structured, numbered plan.");
        sb.AppendLine("Do NOT execute the plan. Respond STRICTLY in JSON with the following structure:");
        sb.AppendLine("{ \"plan\": [ { \"step\": 1, \"title\": \"...\", \"description\": \"...\" }, ... ] }");
    }
    else if (mode == "execute")
    {
        sb.AppendLine("You must now execute the following plan step by step:");
        sb.AppendLine(planJson);
        sb.AppendLine("Execute the plan thoroughly and clearly.");
    }
    /*else
    {
        sb.AppendLine("Answer the user's question directly.");
    }*/

    sb.AppendLine();
    sb.AppendLine("User:");

    // --- Caveman Compression Mode ---
    if (caveman == "true")
    {
        sb.AppendLine(@"
You are a caveman compression expert. Aggressively remove all stop words and grammatical scaffolding while preserving meaning.

CORE STRATEGY:
1. Remove articles, auxiliary verbs, and redundant words. Keep only content words that carry semantic meaning.
2. Use simple, common words. If there's a simpler word, use it. Think like a caveman.

ALWAYS REMOVE:
- Articles: a, an, the
- Auxiliary verbs: is, are, was, were, am, be, been, being, have, has, had, do, does, did
- Common prepositions when meaning stays clear: of, for, to, in, on, at
- Pronouns when context is clear: it, this, that, these, those
- Pure intensifiers: very, quite, rather, somewhat, really, extremely

ALWAYS KEEP:
- All nouns (people, places, things, concepts)
- All main verbs (actions, not auxiliaries)
- All adjectives that add meaning
- All numbers and quantifiers (at least, approximately, more than, 15, many)
- Uncertainty qualifiers (appears, seems, might)
- Critical prepositions that change meaning (from, with, without, stuck to)
- Time/frequency words (every Tuesday, weekly, daily, always, never)
- Names, titles (Dr., Mr., Senator)
- Technical terms and domain-specific language

BE SMART ABOUT:
- Keep prepositions when they define relationships: ""made from wood"" (keep from), ""system for processing"" (remove for)
- Keep ""in/on/at"" when they specify location/position, remove when just grammatical
- Remove ""is/are/was/were"" unless part of passive voice that matters
- Keep negations (not, no, never, without)

Output ONLY the caveman compressed text, nothing else.

TEXT TO COMPRESS:
");
    }

    sb.AppendLine(prompt);

    // Attach uploaded files
    if (files != null && files.Any())
    {
        sb.AppendLine("\nAttached files:");
        foreach (var file in files)
        {
            using var reader = new StreamReader(file.OpenReadStream());
            var content = reader.ReadToEnd();
            sb.AppendLine($"- {file.FileName}: {content}");
        }
    }

    return sb.ToString();
}








    public IActionResult Privacy()
    {
        return View();
    }

    [ResponseCache(Duration = 0, Location = ResponseCacheLocation.None, NoStore = true)]
    public IActionResult Error()
    {
        return View(new ErrorViewModel { RequestId = Activity.Current?.Id ?? HttpContext.TraceIdentifier });
    }
}
