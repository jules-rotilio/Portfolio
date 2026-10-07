// HomeController.cs
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Diagnostics;
using System.Text;
using WebCsharp.Views.Home;
namespace WebCsharp.Models
{

    public class HomeController : Controller
    {
        private readonly IConfiguration _configuration;
        private readonly ILogger<HomeController> _logger;

        // Constructor that accepts IConfiguration
        public HomeController(IConfiguration configuration, ILogger<HomeController> logger)
        {
            _configuration = configuration;
            _logger = logger;
        }

        [HttpPost]
        public IActionResult RunCode(CodeViewModel model)
        {   
            
            if (ModelState.IsValid)
            {
                if(model.Authorization != _configuration["Authorization"])
                {
                    ViewBag.Output = "Invalid authorization.";
                    _logger.LogWarning("Invalid authorization from {IP}", HttpContext.Connection.RemoteIpAddress);
                    return View("Index");
                }
                // Step 1: Create a Temporary Project
                var projectDir = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
                Directory.CreateDirectory(projectDir);
                var codeFilePath = Path.Combine(projectDir, "Program.cs");
                var projectFilePath = Path.Combine(projectDir, $"{Path.GetRandomFileName()}.csproj");

                // Create .csproj file
                System.IO.File.WriteAllText(projectFilePath, @"
<Project Sdk=""Microsoft.NET.Sdk"">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
");

                // Save user code
                System.IO.File.WriteAllText(codeFilePath, model.UserCode);

                // Step 2: Run the Project
                var startInfo = new ProcessStartInfo
                {
                    FileName = "dotnet",
                    Arguments = $"run --project {projectFilePath}",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WorkingDirectory = projectDir
                };
                var executeProcess = Process.Start(startInfo);
                executeProcess.WaitForExit();

                // Step 3: Capture Output
                ViewBag.Output = executeProcess.StandardOutput.ReadToEnd() + "\n" + executeProcess.StandardError.ReadToEnd();
                //replace your username with "user" in the output
                #pragma warning disable CA1416
                ViewBag.Output = ViewBag.Output.Replace(System.Security.Principal.WindowsIdentity.GetCurrent().Name, "user");
                #pragma warning restore CA1416
                ViewBag.Output = ViewBag.Output.Replace(Environment.UserName, "user");
                //clean up the temp directory
                Directory.Delete(projectDir, true);
            }
            else
            {
                ViewBag.Output = "Invalid model state.";
                _logger.LogWarning("Invalid model state from {IP}", HttpContext.Connection.RemoteIpAddress);
            }
            
            return View("Index");
        }

        [HttpGet]
        public IActionResult Index()
        {
            var model = new CodeViewModel(){
                UserCode = "Console.WriteLine(\"Hello World!\");"
            };
            return View(model);
        }

        [HttpGet]
        public IActionResult Privacy()
        {
            return View();
        }
    }


}

