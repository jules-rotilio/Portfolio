public interface IOllamaModelService
{
    IReadOnlyList<string> Models { get; }
    Task RefreshAsync();
}