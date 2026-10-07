using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;


namespace InstallAndUpdateSoftwares
{
    partial class InstallAndUpdateSoftwares
    {
        //static void Main() => Program().GetAwaiter().GetResult();
        static void Main() {
            string lv = GetFirefoxLatestVersion().GetAwaiter().GetResult();
            Console.WriteLine(lv);
        }


        // configuration variable: configurationbuilder built
        static readonly IConfiguration Sources = new ConfigurationBuilder().AddJsonFile("Sources.json").Build();
        static readonly IConfiguration Response = new ConfigurationBuilder().AddJsonFile("Response.json").Build();
        static async Task<int> Program()
        {

            foreach (var ReponseSection in Response.GetChildren())
            {
                string Software = ReponseSection.Key;
                bool InstallInstruction = bool.Parse(ReponseSection.Value);
                if (Sources.GetSection(Software).Exists())
                {
                    IConfigurationSection SourceSection = Sources.GetSection(Software);
                    string Version = await GetVersion(Software);
                    if (Version != "")
                    {
                        Console.WriteLine($"{Software}'s latests version's number is {Version}.");
                    }
                    else
                    {
                        Console.WriteLine($"Something went wrong while getting the version of {Software}.");
                    }
                    string Source = Sources.GetSection(Software).GetSection("SetupUrl").Value;
                    Source = string.Format(Source, Version);
                    if (InstallInstruction)
                    {
                        Console.WriteLine($"Installing {Software} from {Source}");
                        string Extension = SourceSection.GetSection("Extension").Value;
                        string SetupPath = await Download(Source, Extension);
                        string SetupExecutable = SourceSection.GetSection("SetupExecutable").Value;
                        if (SetupExecutable != null)
                        {
                            string SoftwarePath = SourceSection.GetSection("SoftwarePath").Value;
                            string SoftwareArgs = SourceSection.GetSection("SoftwareArgs").Value;
                            if (Install(SetupExecutable, SoftwarePath, SoftwareArgs))
                            {
                                Console.WriteLine($"{Software} has been installed successfully.");
                            }
                            else
                            {
                                Console.WriteLine($"An error occured while installing {Software}.");
                            }
                        }
                        else
                        {
                            Console.WriteLine($"No SetupExecutable found for {Software}.");
                        }
                    }
                }
                else
                {
                    Console.WriteLine($"No source found for {Software}.");
                    Console.WriteLine($"{Software} is not installable using InstallAndUpdateSoftwares, yet.");
                }

            }
            Console.WriteLine("goodbye");
            return 0;
        }
        static async Task<string> GetLatestVersion(string Software)
        {
            string Version = "";
            switch (Software)
            {
                case "PowerShell":
                    Version = await GetPowershellLatestVersion();
                    break;
                /*case "Git":
                    Version = await GetGitLatestVersion();
                    break;
                case "Python":
                    Version = await GetPythonLatestVersion();
                    break;
                case "NodeJS":
                    Version = await GetNodeJSLatestVersion();
                    break;
                case "VSCode":
                    Version = await GetVSCodeLatestVersion();
                    break;*/
                default:
                    break;
            }
            return Version;
        }
        static async Task<string> GetCurrentVersion(string Software)
        {
            string Version = "";
            switch (Software)
            {
                case "PowerShell":
                    Version = await GetPowershellCurrentVersion();
                    break;
                /*case "Git":
                    Version = await GetGitLatestVersion();
                    break;
                case "Python":
                    Version = await GetPythonLatestVersion();
                    break;
                case "NodeJS":
                    Version = await GetNodeJSLatestVersion();
                    break;
                case "VSCode":
                    Version = await GetVSCodeLatestVersion();
                    break;*/
                default:
                    break;
            }
            return Version;
        }

        static async Task<string> Download(string url, string extension)
        {
            using HttpClient client = new();
            // Get the file data
            Console.WriteLine(url);
            byte[] data = await client.GetByteArrayAsync(url);

            // Create a temporary file with a .msi extension
            string tempFile = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName() + extension);

            // Write the data to the temporary file
            await File.WriteAllBytesAsync(tempFile, data);

            return tempFile;
        }
        static bool Install(string SetupExecutable, string SoftwarePath, string SoftwareArgs)
        {
            if(SetupExecutable != null)
            {
                SoftwareArgs = string.Format(SoftwareArgs, SoftwarePath);
            }
            else
            {
                SetupExecutable = SoftwarePath;
            }
            ProcessStartInfo psi = new()
            {
                FileName = SetupExecutable,
                Arguments = string.Format(SoftwareArgs),
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using Process? process = Process.Start(psi);
            process?.WaitForExit();
            if (process?.ExitCode == 0)
            {
                return true;
            }
            else
            {
                return false;
            }
        }
    }
}