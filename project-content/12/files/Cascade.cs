using Discord;
using Discord.Rest;
using Discord.Interactions;
using Discord.WebSocket;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

/* 
using System.Globalization;
using System.Xml.Linq;
using System.Xml;
using System.Text.RegularExpressions;
using System.ServiceModel.Syndication;
using Discord.Net;
using Newtonsoft.Json;
using System.Reflection;
using Formatting = Newtonsoft.Json.Formatting;
using Color = Discord.Color;
using Microsoft.Data.Sqlite;
using System.Data.SqlClient;
*/
using System.Diagnostics;
using System.ServiceModel.Syndication;
using System.Xml;

namespace Cascade
{

    public class Cascade
    {
        private readonly IConfiguration _configuration;
        private readonly IServiceProvider _services;
        private readonly DiscordSocketClient _client;

        private readonly DiscordSocketConfig _socketConfig = new()
        {
            GatewayIntents = GatewayIntents.AllUnprivileged | GatewayIntents.GuildMembers,
            AlwaysDownloadUsers = true,
        };

        public Cascade()
        {
            _configuration = new ConfigurationBuilder()
                .AddJsonFile("appsettings.json", optional: false)
                .Build();

            _services = new ServiceCollection()
                .AddSingleton(_configuration)
                .AddSingleton(_socketConfig)
                .AddSingleton<DiscordSocketClient>()
                .AddSingleton(x => new InteractionService(x.GetRequiredService<DiscordSocketClient>()))
                .AddSingleton<InteractionHandler>()
                .BuildServiceProvider();
            _client = _services.GetRequiredService<DiscordSocketClient>();
        }

        static void Main() => new Cascade()
            .RunAsync()
            .GetAwaiter()
            .GetResult();


        public async Task RunAsync()
        {
            var con = Connection.GetInstance(_configuration);
            con.InitDB();

            _client.Log += Log;
            await _services.GetRequiredService<InteractionHandler>().InitializeAsync();

            await _client.LoginAsync(TokenType.Bot, _configuration["token"]);
            await _client.StartAsync();

            var timer = new PeriodicTimer(TimeSpan.FromMinutes(2));
            while (await timer.WaitForNextTickAsync())
            {
                Console.WriteLine(DateTime.Now);
                con = Connection.GetInstance(_configuration);
                var command = con.CreateCommand();
                command.CommandText = "SELECT Channel_ID,Url_Rss,Color,LAST_ID FROM RssChannel";
                using (var reader = await command.ExecuteReaderAsync())
                {
                    while (await reader.ReadAsync())
                    {
                        var Channel_ID = UInt64.Parse(reader.GetString(0));
                        var URLRSS = reader.GetString(1);
                        var color = uint.Parse(reader.GetString(2));
                        var LASTID = reader.GetString(3);
                        Console.WriteLine($"Channel_ID = {Channel_ID}, URLRSS = {URLRSS}, Color = {color}, LASTID = {LASTID}");

                        Debug.WriteLine("test 1");
                        var last_date = DateTimeOffset.FromFileTime(long.Parse(LASTID));
                        var channel = _client.GetChannel(Channel_ID);

                        ulong guildId = (channel as SocketGuildChannel)?.Guild.Id ?? 0;

                        if (guildId != 0)
                        {
                            SocketGuild guild = _client.GetGuild(guildId);

                            if (guild != null)
                            {
                                SocketTextChannel socketTextChannel = guild.GetTextChannel(channel.Id);

                                if (socketTextChannel != null)
                                {
                                    last_date = await Tools.RssReader(url: URLRSS, discordChannel: socketTextChannel, color: color, dateOfLastItem: last_date, con: con, publish: true);
                                    con.Edit_Channel_Row(cid: Channel_ID, date: last_date.ToFileTime());
                                }
                            }
                        }

                    }
                }
                con.Close();
            }
        }


        private Task Log(LogMessage message)
        {
            Console.WriteLine(message.ToString());
            return Task.CompletedTask;
        }

        public static bool IsDebug()
        {
#if DEBUG
            return true;
#else
				return false;
#endif
        }
    }
}
