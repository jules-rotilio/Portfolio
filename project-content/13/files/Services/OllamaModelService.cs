using System.Text.Json;

public class OllamaModelService : IOllamaModelService
{
    private readonly HttpClient _httpClient;

    public IReadOnlyList<string> Models { get; private set; } = new List<string>();

    public OllamaModelService(IHttpClientFactory httpClientFactory)
    {
        // Initialize the HTTP client with the name "ollama"
        _httpClient = httpClientFactory.CreateClient("ollama");

        // Call Ollama to fetch models only once at startup
        Models = FetchModelsAsync().GetAwaiter().GetResult();
    }

    public async Task RefreshAsync()
    {
        Models = FetchModelsAsync().GetAwaiter().GetResult();
    }

    private async Task<IReadOnlyList<string>> FetchModelsAsync()
    {
        var response = await _httpClient.GetAsync("/api/tags");
        response.EnsureSuccessStatusCode();

        var json = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(json);

        var models = new List<string>();
        foreach (var model in doc.RootElement.GetProperty("models").EnumerateArray())
        {
            models.Add(model.GetProperty("name").GetString()!);
        }

        return models;
    }
}
