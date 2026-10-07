using System.Diagnostics;
using System.Text.Json;

namespace InstallAndUpdateSoftwares
{
    partial class InstallAndUpdateSoftwares
    {
        static async Task<string> GetPowershellLatestVersion()
        {
            string githubReleaseUrl = "https://api.github.com/repos/PowerShell/powershell/releases/latest";
            using HttpClient client = new();
            client.DefaultRequestHeaders.Add("User-Agent", "request");
            string json_s = await client.GetStringAsync(githubReleaseUrl);

            JsonElement json = JsonSerializer.Deserialize<JsonElement>(json_s);

            if (json.TryGetProperty("tag_name", out var tagValue))
            {
                string tagValue_s = tagValue.ToString().Replace("v", "");
                //Console.WriteLine($"Valeur de tag_name : {tagValue_s}");
                return tagValue_s;
            }
            else
            {
                return "";
            }

        }
        static string GetPowershellCurrentVersion()
        {
            ProcessStartInfo psi = new()
            {
                FileName = "pwsh",
                Arguments = "-Command $PSVersionTable.PSVersion.ToString()",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using Process? process = Process.Start(psi);
            string? output = process?.StandardOutput?.ReadToEnd();
            return output ?? "None";
        }
    }
}