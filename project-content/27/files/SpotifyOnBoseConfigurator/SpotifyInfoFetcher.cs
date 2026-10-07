using SpotifyAPI.Web;
using SpotifyOnBoseConfigurator;
using System;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

public class SpotifyInfoFetcher
{
    public static async Task<string> FetchSpotifyInfo(string spotifyUrl)
    {
        var config = SpotifyClientConfig.CreateDefault();
        var request = new ClientCredentialsRequest("<REDACTED>", "<REDACTED>");
        var oauthclient = new OAuthClient(config);
        var response = await oauthclient.RequestToken(request);

        var spotify = new SpotifyClient(config.WithToken(response.AccessToken));

        string urlType = DetectSpotifyUrl(spotifyUrl);

        if (urlType == "album")
        {
            // Récupérer le nom de l'album et son artiste
            var albumId = spotifyUrl.Split('/').Last().Split('?')[0];
            var album = await spotify.Albums.Get(albumId);

            if (album.Artists.Count > 1)
            {
                var artists = string.Join(", ", album.Artists.Select(a => a.Name));
                return $"{artists} - {album.Name}";
            }
            else
            {
                return $"{album.Artists.First().Name} - {album.Name}";


            }
        }
        else if (urlType == "track")
        {
            // Récupérer le nom de la chanson et son artiste
            var trackId = spotifyUrl.Split('/').Last().Split('?')[0];
            var track = await spotify.Tracks.Get(trackId);
            if (track.Artists.Count > 1)
            {
                var artists = string.Join(", ", track.Artists.Select(a => a.Name));
                return $"{artists} - {track.Name}";
            }
            else
            {
                return $"{track.Artists.First().Name} - {track.Name}";
            }
        }
        else if (urlType == "playlist")
        {
            try
            {
                // Récupérer le nom de la playlist
                var playlistId = spotifyUrl.Split('/').Last().Split('?')[0];
                var playlist = await spotify.Playlists.Get(playlistId);
                return playlist.Name;
            }
            catch (APIException e)
            {
                if (e.Message.Equals("Resource not found"))
                {
                    var tcs = new TaskCompletionSource<string>();
                    PlaylistNotFound PNF = new ();
                    PNF.Show();
                    PNF.ValiderClicked += (playlistName) =>
                    {
                        tcs.SetResult(playlistName);
                    };
                    return await tcs.Task;

                }
                else
                {
                    return "Error fetching playlist";
                }
            }
            catch (Exception e)
            {
                return "Error fetching playlist";
            }
        }
        else if (urlType == "artist")
        {
            // Récupérer le nom de l'artiste
            var artistId = spotifyUrl.Split('/').Last().Split('?')[0];
            var artist = await spotify.Artists.Get(artistId);
            return artist.Name;
        }
        return "Unknown URL type";
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
                return "unknown";
            }
        }
        else
        {
            throw new ArgumentException("Invalid Spotify URL");
        }
    }
}
