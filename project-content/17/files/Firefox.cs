using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace InstallAndUpdateSoftwares
{
    partial class InstallAndUpdateSoftwares
    {
        static async Task<string> GetFirefoxLatestVersion()
        {
            string latestVersion = "";
            using (HttpClient client = new HttpClient())
            {
                string url = "https://www.mozilla.org/en-US/firefox/notes/";
                string pageContent = await client.GetStringAsync(url);
                Regex regex = FirefoxRegex();
                Match match = regex.Match(pageContent);
                if (match.Success)
                {
                    latestVersion = match.Groups[1].Value;
                }
            }
            return latestVersion;
        }

        static string GetFirefoxCurrentVersion()
        {
            try
            {
                FileVersionInfo fileVersionInfo = FileVersionInfo.GetVersionInfo("C:\\Program Files\\Mozilla Firefox\\firefox.exe");
                string currentVersion = fileVersionInfo.ProductVersion;

                return currentVersion;
            }
            catch (FileNotFoundException)
            {
                Console.WriteLine("Firefox not found");
                return "";
            }
        }

        [GeneratedRegex(@"<span class=""c-release-version"">(\d+\.\d+\.\d+)</span>", RegexOptions.Singleline)]
        private static partial Regex FirefoxRegex();
    }
}
