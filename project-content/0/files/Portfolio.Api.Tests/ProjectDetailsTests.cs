using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Portfolio.Api.Tests
{
    /// <summary>GET /api/projects/{id} et fichiers associés, sur un dossier de contenu temporaire.</summary>
    public class ProjectDetailsTests : IDisposable
    {
        // Le projet 5 existe dans Projects.json ; le projet 1 existe mais n'a pas de contenu ici
        private const int Id = 5;
        private static readonly byte[] Png = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 0];

        private readonly string _root = Path.Combine(Path.GetTempPath(), "portfolio-content-" + Guid.NewGuid());
        private readonly WebApplicationFactory<Program> _factory;
        private readonly HttpClient _client;

        public ProjectDetailsTests()
        {
            var project = Path.Combine(_root, Id.ToString());
            Write(project, "project.json", """
                { "longDescription": "Longue description.\n\n- Point A", "allowZipDownload": false,
                  "images": [ { "file": "ecran.png", "alt": "Écran", "caption": "Accueil" }, { "file": "absente.png", "alt": "?" } ] }
                """);
            Write(project, "images/ecran.png", Png);
            Write(project, "files/README.md", "# Projet\n");
            Write(project, "files/src/main.py", "print('ok')\n");
            Write(project, "files/src/icone.png", Png);
            Write(project, "files/.env", "SECRET=1");
            Write(project, "files/.git/config", "[core]");
            Write(project, "files/src/__pycache__/main.cpython-312.pyc", Png);
            Write(project, "files/gros.txt", new string('a', 70 * 1024));
            Write(project, "files/latin1.txt", new byte[] { 0x63, 0x61, 0x66, 0xE9 }); // « café » en Latin-1 : pas de l'UTF-8

            _factory = new WebApplicationFactory<Program>().WithWebHostBuilder(b => b.UseSetting("ProjectContent:Path", _root));
            _client = _factory.CreateClient();
        }

        public void Dispose()
        {
            _client.Dispose();
            _factory.Dispose();
            Directory.Delete(_root, recursive: true);
        }

        private static void Write(string directory, string relativePath, object content)
        {
            var path = Path.Combine(directory, relativePath);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            if (content is byte[] bytes) File.WriteAllBytes(path, bytes);
            else File.WriteAllText(path, (string)content);
        }

        private void AllowZip() =>
            File.WriteAllText(Path.Combine(_root, Id.ToString(), "project.json"), """{ "allowZipDownload": true }""");

        private async Task<JsonElement> Details() =>
            await _client.GetFromJsonAsync<JsonElement>($"/api/projects/{Id}");

        private static JsonElement Node(JsonElement nodes, string name) =>
            nodes.EnumerateArray().Single(n => n.GetProperty("name").GetString() == name);

        [Theory]
        [InlineData(999)] // projet inconnu
        [InlineData(1)]   // projet sans contenu détaillé : le front se rabat sur la carte
        public async Task Details_WithoutContent_Returns404(int id)
        {
            Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync($"/api/projects/{id}")).StatusCode);
        }

        [Fact]
        public async Task Details_CombineTheCardAndTheContentFolder()
        {
            var details = await Details();

            Assert.Equal(Id, details.GetProperty("id").GetInt32());
            Assert.Equal("MediaToolkit", details.GetProperty("name").GetString());
            Assert.NotEqual(0, details.GetProperty("technologies").GetArrayLength());
            Assert.Equal("Longue description.\n\n- Point A", details.GetProperty("longDescription").GetString());
            Assert.Equal(JsonValueKind.Null, details.GetProperty("zipUrl").ValueKind);

            // Les images absentes du dossier sont ignorées
            var image = Assert.Single(details.GetProperty("images").EnumerateArray());
            Assert.Equal($"/api/projects/{Id}/images/ecran.png", image.GetProperty("url").GetString());
            Assert.Equal("Accueil", image.GetProperty("caption").GetString());
        }

        [Fact]
        public async Task Details_FileTree_ShowsSources_AndNeverSecretsOrCaches()
        {
            var files = (await Details()).GetProperty("files");

            Assert.Equal(["src", "gros.txt", "latin1.txt", "README.md"], files.EnumerateArray().Select(n => n.GetProperty("name").GetString()));

            var src = Node(files, "src");
            Assert.Equal("directory", src.GetProperty("type").GetString());
            Assert.Equal(["icone.png", "main.py"], src.GetProperty("children").EnumerateArray().Select(n => n.GetProperty("name").GetString()));

            var main = Node(src.GetProperty("children"), "main.py");
            Assert.Equal("src/main.py", main.GetProperty("path").GetString());
            Assert.Equal("print('ok')\n", main.GetProperty("content").GetString());
            Assert.Equal($"/api/projects/{Id}/files/src/main.py", main.GetProperty("url").GetString());

            // Binaires, fichiers trop gros ou mal encodés : pas de contenu, seulement l'URL
            Assert.Equal(JsonValueKind.Null, Node(src.GetProperty("children"), "icone.png").GetProperty("content").ValueKind);
            Assert.Equal(JsonValueKind.Null, Node(files, "gros.txt").GetProperty("content").ValueKind);
            Assert.Equal(JsonValueKind.Null, Node(files, "latin1.txt").GetProperty("content").ValueKind);
        }

        [Fact]
        public async Task Files_ImagesAreShown_OtherFilesAreDownloads()
        {
            var image = await _client.GetAsync($"/api/projects/{Id}/files/src/icone.png");
            Assert.Equal("image/png", image.Content.Headers.ContentType?.MediaType);
            Assert.Contains("sandbox", image.Headers.GetValues("Content-Security-Policy").Single());

            var source = await _client.GetAsync($"/api/projects/{Id}/files/src/main.py");
            Assert.Equal("application/octet-stream", source.Content.Headers.ContentType?.MediaType);
            Assert.Equal("attachment", source.Content.Headers.ContentDisposition?.DispositionType);

            var preview = await _client.GetAsync($"/api/projects/{Id}/images/ecran.png");
            Assert.Equal(HttpStatusCode.OK, preview.StatusCode);
        }

        [Theory]
        [InlineData("files/..%2Fproject.json")]          // sortie du dossier files/
        [InlineData("files/..%2F..%2F1%2Fproject.json")] // vers un autre projet
        [InlineData("files/.env")]                       // secret copié par erreur
        [InlineData("files/.git/config")]
        [InlineData("files/absent.txt")]
        [InlineData("images/..%2Fproject.json")]
        public async Task Files_OutsideTheFolderOrIgnored_Return404(string path)
        {
            Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync($"/api/projects/{Id}/{path}")).StatusCode);
        }

        [Fact]
        public async Task Zip_IsOnlyAvailableWhenExplicitlyAllowed()
        {
            Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync($"/api/projects/{Id}/zip")).StatusCode);

            AllowZip();
            Assert.Equal($"/api/projects/{Id}/zip", (await Details()).GetProperty("zipUrl").GetString());

            var response = await _client.GetAsync($"/api/projects/{Id}/zip");
            Assert.Equal("application/zip", response.Content.Headers.ContentType?.MediaType);
            Assert.Equal("MediaToolkit.zip", response.Content.Headers.ContentDisposition?.FileName?.Trim('"'));

            using var zip = new ZipArchive(await response.Content.ReadAsStreamAsync());
            Assert.Equal(["gros.txt", "latin1.txt", "README.md", "src/icone.png", "src/main.py"], zip.Entries.Select(e => e.FullName).OrderBy(n => n, StringComparer.OrdinalIgnoreCase));
        }

        [Fact]
        public async Task SymbolicLinks_AreNeverFollowed()
        {
            var outside = Path.Combine(_root, "secret.txt");
            File.WriteAllText(outside, "ne doit pas sortir");
            File.CreateSymbolicLink(Path.Combine(_root, Id.ToString(), "files", "lien.txt"), outside);

            Assert.DoesNotContain("lien.txt", (await _client.GetStringAsync($"/api/projects/{Id}")));
            Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync($"/api/projects/{Id}/files/lien.txt")).StatusCode);
        }
    }
}
