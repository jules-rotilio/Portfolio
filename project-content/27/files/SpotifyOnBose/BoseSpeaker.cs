using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Xml;

namespace SpotifyAlarmClockOnBose
{
    internal class BoseSpeaker
    {
        private string _url;
        internal BoseSpeaker(string url)
        {
            _url = url;

            sourceAccount = "spotify.user.id";
        }

        private string sourceAccount = "";

        public static string GetIDFromUrl(string url)
        {
            Uri uri = new Uri(url);
            string[] segments = uri.Segments;
            string trackID = segments[segments.Length - 1].TrimEnd('?');
            return trackID;
        }

        public async Task Play(string URL)
        {
            var client = new HttpClient();
            string URLType = DetectSpotifyUrl(URL);
            string id = GetIDFromUrl(URL);
            string payload = $@"
            <ContentItem source=""SPOTIFY"" type=""uri"" location=""spotify:{URLType}:{id}"" sourceAccount=""{sourceAccount}"" isPresetable=""true""/>
        ";

            await client.PostAsync($"{_url}/select", new StringContent(payload));

            await Task.Delay(1000);

            while (await IsBuffering())
            {
                await Task.Delay(500);
            }
        }

        private static string DetectSpotifyUrl(string url)
        {
            // Regex to match Spotify URLs
            string pattern = @"^(https?://)?(www\.)?(spotify\.com|open\.spotify\.com)(/intl-fr)?/(track|album|playlist|artist)/([a-zA-Z0-9]+)";
            // Check if the URL matches the pattern
            if (Regex.IsMatch(url, pattern))
            {
                string trackpattern = @"^(https?://)?(www\.)?(spotify\.com|open\.spotify\.com)(/intl-fr)?/track/([a-zA-Z0-9]+)";
                string albumpattern = @"^(https?://)?(www\.)?(spotify\.com|open\.spotify\.com)(/intl-fr)?/album/([a-zA-Z0-9]+)";
                string playlistpattern = @"^(https?://)?(www\.)?(spotify\.com|open\.spotify\.com)(/intl-fr)?/playlist/([a-zA-Z0-9]+)";
                string artistpattern = @"^(https?://)?(www\.)?(spotify\.com|open\.spotify\.com)(/intl-fr)?/artist/([a-zA-Z0-9]+)";
                if (Regex.IsMatch(url, trackpattern))
                {
                    return "track";
                }
                else if (Regex.IsMatch(url, albumpattern))
                {
                    return "album";
                }
                else if (Regex.IsMatch(url, playlistpattern))
                {
                    return "playlist";
                }
                else if (Regex.IsMatch(url, artistpattern))
                {
                    return "artist";
                }
                else
                {
                    throw new ArgumentException("Invalid Spotify URL");
                }
            }
            else
            {
                throw new ArgumentException("Invalid Spotify URL");
            }
        }

        public async Task Pause()
        {
            await PressKey("PAUSE");
        }

        public async Task ShuffleOn()
        {
            await PressKey("SHUFFLE_ON");
        }

        public async Task ShuffleOff()
        {
            await PressKey("SHUFFLE_OFF");
        }

        public async Task SetVolume(int vol)
        {
            var client = new HttpClient();
            await client.PostAsync($"{_url}/volume", new StringContent($"<volume>{vol}</volume>"));
        }

        public async Task TurnOff()
        {
            await PressKey("POWER");
        }

        async Task PressKey(string key)
        {
            var client = new HttpClient();
            string payload = $"<key state=\"press\" sender=\"Gabbo\">{key}</key>";
            string payload2 = $"<key state=\"release\" sender=\"Gabbo\">{key}</key>";
            await client.PostAsync($"{_url}/key", new StringContent(payload));
            await client.PostAsync($"{_url}/key", new StringContent(payload2));
        }

        async Task<HttpResponseMessage?> GetStatus()
        {
            var client = new HttpClient();
            var response = await client.GetAsync($"{_url}/now_playing");
            return response;
        }

        public async Task<int> GetProgress()
        {
            var response = await GetStatus(); // <time total="241">1</time>
            int progress;
            using (XmlReader reader = XmlReader.Create(await response.Content.ReadAsStreamAsync()))
            {
                while (reader.Read())
                {
                    if (reader.NodeType == XmlNodeType.Element)
                    {
                        if (reader.Name == "time")
                        {
                            string total = reader.GetAttribute("total");
                            string current = reader.ReadElementContentAsString();
                            progress = int.Parse(current) * 100 / int.Parse(total);
                            return progress;
                        }
                    }
                }
            }
            return 1;
        }

        async Task<bool> IsBuffering()
        {
            Tuple<string, string?> status = await GetSourceAndPlayState();
            if ((status.Item1 == "LOCAL" || status.Item1 == "STANDBY" || status.Item1 == "INVALID_SOURCE") || (status.Item1 == "SPOTIFY" && status.Item2 == "BUFFERING_STATE"))
            {
                return true;
            }
            return false;
        }

        async Task<Tuple<string, string?>> GetSourceAndPlayState()
        {
            var response = await GetStatus();
            string source = "";
            string? playStatus = null;
            using (XmlReader reader = XmlReader.Create(await response.Content.ReadAsStreamAsync()))
            {
                while (reader.Read())
                {
                    if (reader.NodeType == XmlNodeType.Element)
                    {
                        if (reader.Name == "nowPlaying")
                        {
                            source = reader.GetAttribute("source");
                        }
                        if (reader.Name == "playStatus")
                        {
                            playStatus = reader.ReadElementContentAsString();
                        }
                    }
                }
            }
            return new Tuple<string, string?>(source, playStatus);
        }

        public async Task<string?> GetTrack()
        {
            var response = await GetStatus();
            string? trackId = "";
            using (XmlReader reader = XmlReader.Create(await response.Content.ReadAsStreamAsync()))
            {
                while (reader.Read())
                {
                    if (reader.NodeType == XmlNodeType.Element)
                    {
                        if (reader.Name == "trackID")
                        {
                            trackId = reader.ReadElementContentAsString();
                        }
                    }
                }
            }
            return trackId;
        }

        public async Task StorePresetPlaylist(int preset, string playlistID)
        {
            var client = new HttpClient();
            string payload = $@"
            <preset id=""{preset}"" createdOn=""{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}"" updatedOn=""{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}"">
                <ContentItem source=""SPOTIFY"" type=""uri"" location=""spotify:playlist:{playlistID}"" sourceAccount=""{sourceAccount}"" isPresetable=""true""/>
            </preset>";

            Console.WriteLine(payload);
            var response = await client.PostAsync($"{_url}/storePreset", new StringContent(payload));
            Console.WriteLine(response);
        }
        public async Task StorePresetTrack(int preset, string trackID)
        {
            var client = new HttpClient();
            string payload = $@"
            <preset id=""{preset}"" createdOn=""{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}"" updatedOn=""{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}"">
                <ContentItem source=""SPOTIFY"" type=""uri"" location=""spotify:track:{trackID}"" sourceAccount=""{sourceAccount}"" isPresetable=""true""/>
            </preset>";
            await client.PostAsync($"{_url}/storePreset", new StringContent(payload));
        }

        public async Task RemovePreset(int preset)
        {
            var client = new HttpClient();
            string payload = $@"<preset id=""{preset}""></preset>";
            await client.PostAsync($"{_url}/removePreset", new StringContent(payload));
        }
        public async Task PlayPreset(int preset)
        {
            await PressKey($"PRESET_{preset}");
        }
    }

    internal class BoseNotFoundException : Exception
    {
        public BoseNotFoundException(string? message) : base(message) { }
    }
}
