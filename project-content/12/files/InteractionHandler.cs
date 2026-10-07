using Discord.Interactions;
using Discord.Net;
using Discord.WebSocket;
using Discord;
using Microsoft.Extensions.Configuration;
using Newtonsoft.Json;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;

namespace Cascade
{
    public class InteractionHandler(DiscordSocketClient client, InteractionService handler, IServiceProvider services, IConfiguration config)
    {
        private readonly DiscordSocketClient _client = client;
        private readonly InteractionService _handler = handler;
        private readonly IServiceProvider _services = services;
        private readonly IConfiguration _configuration = config;

        public async Task InitializeAsync()
        {
            // Process when the client is ready, so we can register our commands.
            _client.Ready += ReadyAsync;
            _handler.Log += Log;
            _client.Ready += Client_Ready;
            _client.SlashCommandExecuted += SlashCommandHandler;


            // Add the public modules that inherit InteractionModuleBase<T> to the InteractionService
            await _handler.AddModulesAsync(Assembly.GetEntryAssembly(), _services);

            // Process the InteractionCreated payloads to execute Interactions commands
            _client.InteractionCreated += HandleInteraction;
        }

        private Task Log(LogMessage message)
        {
            Console.WriteLine(message.ToString());
            return Task.CompletedTask;
        }


        private async Task ReadyAsync()
        {
            // Context & Slash commands can be automatically registered, but this process needs to happen after the client enters the READY state.
            // Since Global Commands take around 1 hour to register, we should use a test guild to instantly update and test our commands.
            if (Cascade.IsDebug())
            {

                await _handler.RegisterCommandsToGuildAsync(_configuration.GetValue<ulong>("testGuild"), true);
                await _handler.RegisterCommandsGloballyAsync(true);
            }
            else
                await _handler.RegisterCommandsGloballyAsync(true);
        }

        private async Task HandleInteraction(SocketInteraction interaction)
        {
            try
            {
                // Create an execution context that matches the generic type parameter of your InteractionModuleBase<T> modules.
                var context = new SocketInteractionContext(_client, interaction);

                // Execute the incoming command.
                var result = await _handler.ExecuteCommandAsync(context, _services);

                if (!result.IsSuccess)
                    switch (result.Error)
                    {
                        case InteractionCommandError.UnmetPrecondition:
                            // implement
                            break;
                        default:
                            break;
                    }
            }
            catch
            {
                // If Slash Command execution fails it is most likely that the original interaction acknowledgement will persist. It is a good idea to delete the original
                // response, or at least let the user know that something went wrong during the command execution.
                if (interaction.Type is InteractionType.ApplicationCommand)
                    await interaction.GetOriginalResponseAsync().ContinueWith(async (msg) => await msg.Result.DeleteAsync());
            }
        }
        public async Task Client_Ready()
        {
            var guild = _client.GetGuild(_configuration.GetValue<ulong>("testGuild"));



            var stopbot = new SlashCommandBuilder();
            stopbot.WithName("stop-bot");
            stopbot.WithDescription("This shuts down the bot");


            var addrss = new SlashCommandBuilder()
            .WithName("add-rss")
            .WithDescription("Ajouter un flux rss avec cette commande")
            .AddOption("url", ApplicationCommandOptionType.String, "url entière (https://www.website.com/feed) du flux rss", isRequired: true)
            .AddOption("channel", ApplicationCommandOptionType.String, "nom du channel dans lequel le flux rss sera ", isRequired: true)
            .AddOption(new SlashCommandOptionBuilder()
                .WithName("color")
                .WithDescription("la couleur du embed")
                .WithRequired(true)
                .AddChoice("Black", 0)
                .AddChoice("Blue", Color.Blue.RawValue)
                .AddChoice("Gold", Color.Gold.RawValue)
                .AddChoice("Green", Color.Green.RawValue)
                .AddChoice("DarkBlue", Color.DarkBlue.RawValue)
                .AddChoice("DarkerGrey", Color.DarkerGrey.RawValue)
                .AddChoice("DarkGreen", Color.DarkGreen.RawValue)
                .AddChoice("DarkMagenta", Color.DarkMagenta.RawValue)
                .AddChoice("DarkOrange", Color.DarkOrange.RawValue)
                .AddChoice("DarkPurple", Color.DarkPurple.RawValue)
                .AddChoice("DarkRed", Color.DarkRed.RawValue)
                .AddChoice("DarkTeal", Color.DarkTeal.RawValue)
                .AddChoice("Orange", Color.Orange.RawValue)
                .AddChoice("Purple", Color.Purple.RawValue)
                .AddChoice("Red", Color.Red.RawValue)
                .AddChoice("Teal", Color.Teal.RawValue)
                .WithType(ApplicationCommandOptionType.Integer)
            );
            var rss = new SlashCommandBuilder();
            rss.WithName("rss");
            rss.WithDescription("rss");

            try
            {
                if (guild != null)
                {
                    await guild.CreateApplicationCommandAsync(stopbot.Build());
                }

                await _client.CreateGlobalApplicationCommandAsync(addrss.Build());
                await _client.CreateGlobalApplicationCommandAsync(rss.Build());
            }
            catch (HttpException exception)
            {
                var json = JsonConvert.SerializeObject(exception.Errors, Formatting.Indented);

                // You can send this error somewhere or just print it to the console, for this example we're just going to print it.
                Console.WriteLine(json);
            }
        }
        private async Task SlashCommandHandler(SocketSlashCommand command)
        {
            var guildid = command.GuildId ?? default;
            switch (command.Data.Name)
            {

                case "add-rss":
                    string url = "";
                    string channel_name = "";
                    uint color = 0;

                    foreach (var data in command.Data.Options)
                    {
                        if ((data.Name == "url") && (data.Value?.ToString() != ""))
                        {
                            url = data.Value?.ToString() ?? "";

                        }
                        else if ((data.Name == "channel") & (data.Value?.ToString() != ""))
                        {
                            channel_name = data.Value?.ToString() ?? "";
                        }
                        else if ((data.Name == "color") & (data.Value?.ToString() != ""))

                        {
                            color = uint.Parse(data.Value?.ToString() ?? "0");
                        }
                    }

                    Console.WriteLine(string.Format("{0}\t{1}\t{2}", channel_name, url, color));

                    string success;
                    string message = "";
                    try
                    {

                        var guild = _client.GetGuild(guildid);
                        Discord.Rest.RestTextChannel restchannel = await guild.CreateTextChannelAsync(name: channel_name);
                        Connection dbconnect = new(_configuration["db_source"]);

                        SocketTextChannel? socketChannel = guild?.GetChannel(restchannel.Id) as SocketTextChannel;



                        if (url != null && socketChannel != null)
                        {
                            await Tools.RssReader(url: url, discordChannel: socketChannel, color: color, dateOfLastItem: DateTimeOffset.MinValue, dbconnect);
                        }
                        if (url != null)
                        {
                            dbconnect.Create_Channel_Row(cid: restchannel.Id, url: url, color: color);
                        }

                        dbconnect.Close();
                        success = "Réussi";
                    }
                    catch (Exception exception)
                    {

                        success = "Echec :";
                        message = exception.Message;
                        Console.Error.WriteLine(exception.StackTrace);
                    }


                    EmbedBuilder embed = new()
                    {
                        Color = new Color(color),
                        Title = command.Data.Name,
                        Description = $@"
							You executed {command.Data.Name}, with the following options :
							channel : {channel_name},
							color   : {color},
							url     : {url}.
                            Result : {success} {message}.
						"
                    };
                    await command.RespondAsync(ephemeral: true, embed: embed.Build());

                    break;

                case "first-global-command":
                    Console.WriteLine($"{command.User.Username} executed {command.CommandName}");
                    await command.RespondAsync($"You executed {command.Data.Name}", ephemeral: true);
                    break;

                case "stop-bot":
                    await command.RespondAsync("Goodbye!");
                    await _client.StopAsync();
                    Console.WriteLine($"Requested program exit by {command.User.Username}, with id {command.User.Id}");
                    Environment.Exit(2);
                    break;

                case "rss":
                    await command.RespondAsync($"You executed {command.Data.Name}", ephemeral: true);
                    Console.WriteLine("\n\n");
                    //await Rss_reader("https://cert.ssi.gouv.fr/alerte/feed", channelid: command.Channel.Id, guildid: guildid, color: Color.Red);
                    Console.WriteLine("\n\n");
                    //await Rss_reader("https://cert.ssi.gouv.fr/avis/feed", channelid: command.Channel.Id, guildid: guildid, color: Color.Orange);
                    Console.WriteLine("\n\n");
                    break;

                default:
                    await command.RespondAsync($"You executed {command.Data.Name}", ephemeral: true);
                    break;

            }
        }
    }
}
