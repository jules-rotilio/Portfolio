using System.ServiceModel.Syndication;
using System.Xml;
using Discord.WebSocket;
using Discord;
using Microsoft.Data.Sqlite;
using System.Globalization;
using System.Text.RegularExpressions;
using Color = Discord.Color;
namespace Cascade
{
    /// <summary>
    /// Classe statique avec des fonctions utiles au nettoyage du contenu des 
    /// <see cref="RssItem">items</see>
    /// </summary>
    public static partial class Tools
    {

        /// <summary>
        /// Supprime les balises HTML d'une chaine de caractères
        /// </summary>
        /// <param name="html"></param>
        /// <returns></returns>
        public static string CleanHtmlString(string html)
        {
            return RemoveDescriptionPrefix(RemoveHtmlTags(html));
        }

        /// <summary>
        /// Supprime les balises HTML d'une chaine de caractères
        /// </summary>
        /// <param name="html"></param>
        /// <returns>La chaine de caractères sans les balises HTML</returns>
        public static string RemoveHtmlTags(string html)
        {
            var doc = new HtmlAgilityPack.HtmlDocument();
            doc.LoadHtml(html);
            return doc.DocumentNode.InnerText;
        }
        public static string RemoveDescriptionPrefix(string description)
        {
            const string prefix = "Description:";
            if (description.StartsWith(prefix))
            {
                description = description[prefix.Length..].Trim();
            }
            return description;
        }

        /*public static string RemoveHTML(string input)
        {
            return RegexRemoveHTML().Replace(input, string.Empty);
        }*/

        public static DateTimeOffset ParseDateTimeOffset(string value)
        {
            string format = "";
            string format1 = "ddd, dd MMM yyyy HH:mm:ss zzz";
            string format2 = "yyyy-MM-dd'T'HH:mm:ss.fff'Z'";
            string format3 = "ddd, dd MMM yyyy HH:mm:ss 'GMT'";
            List<string> searchStrings = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];


            if (value.Contains("GMT"))
            {
                format = format3;
            }
            else if (searchStrings.Any(s => value.Contains(s)))
            {
                format = format1;
            }
            else
            {
                format = format2;
            }
            DateTimeOffset.TryParseExact(value, format, CultureInfo.InvariantCulture, DateTimeStyles.None, out DateTimeOffset date);
            return date;
        }


        public static async Task<DateTimeOffset> RssReader(string url, SocketTextChannel discordChannel, Color color, DateTimeOffset dateOfLastItem, Connection con, bool publish = false)
        {

            SyndicationFeed? feed = null;

            try
            {
                using XmlReader reader = XmlReader.Create(url);
                feed = SyndicationFeed.Load(reader);
            }
            catch (HttpRequestException e)
            {
                Console.WriteLine($"Error {e.StatusCode}: {e.Message}\n{url}\n");
                return dateOfLastItem;
            }
            catch (XmlException e)
            {
                Console.WriteLine($"XML parsing error: {e.Message}\n{url}\n");
                return dateOfLastItem;
            }
            catch (Exception e)
            {
                Console.WriteLine($"Error: {e.Message}\n{url}\n");
                return dateOfLastItem;
            }

            List<SyndicationItem> items;
            if (feed.Items.First().PublishDate.Year != 1)
            {
                items = [.. feed.Items.OrderBy(item => item.PublishDate.ToFileTime())];
            }
            else if (feed.Items.First().LastUpdatedTime.Year != 1)
            {
                   items = [.. feed.Items.OrderBy(item => item.LastUpdatedTime.ToFileTime())];
            }
            else
            {
                return dateOfLastItem;
            }

            var newItems = new List<RssItem>();


            foreach (var item in items)
            {
                string summary = item.Summary != null ? item.Summary.Text : ((TextSyndicationContent)item.Content).Text;
                if (summary.Length > 4096)
                {
                    summary = summary[..4095];
                }

                DateTimeOffset date;
                if (item.PublishDate.Year <= DateTime.Now.Year & item.PublishDate.Year >= DateTime.Now.Year - 5)
                {
                    date = item.PublishDate;
                }
                else if (item.LastUpdatedTime.Year <= DateTime.Now.Year & item.LastUpdatedTime.Year >= DateTime.Now.Year - 5)
                {
                    date = item.LastUpdatedTime;
                }
                else
                {
                    continue;
                }

                var rssItem = new RssItem
                {
                    GUID = item.Id,
                    Title = item.Title.Text,
                    Description = summary,
                    Link = item.Links[0].Uri.ToString() ?? "",
                    PublishDate = date
                };

                if (con.NotExists(rssItem.GUID, rssItem.PublishDate.ToFileTime()) & dateOfLastItem < rssItem.PublishDate)
                {
                    newItems.Add(rssItem);

                    if (publish)
                    {
                        var embed = new EmbedBuilder()
                            .WithTitle(rssItem.Title)
                            .WithUrl(rssItem.Link)
                            .WithColor(color)
                            .WithDescription(CleanHtmlString(rssItem.Description))
                            .WithTimestamp(rssItem.PublishDate)
                            .Build();

                        await discordChannel.SendMessageAsync(null, false, embed);

                        string commandText = @$"
                    INSERT INTO RssItem (GUID, Pub_Date, Channel_Id) VALUES ('{rssItem.GUID}', {rssItem.PublishDate.ToFileTime()}, {discordChannel.Id});
                ";
                        using SqliteCommand command = new(commandText, con);
                        Console.WriteLine(commandText);
                        command.ExecuteNonQuery();
                    }
                }
            }

            return newItems.Count != 0 ? newItems[0].PublishDate : dateOfLastItem;
        }


        [GeneratedRegex("<[a-zA-Z/].*?>")]
        private static partial Regex RegexRemoveHTML();
    }
}
