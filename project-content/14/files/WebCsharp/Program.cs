using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

// Configure Serilog
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Debug() // Set the minimum log level
    .WriteTo.Console() // Continue writing to the console
    #pragma warning disable CS8604
    .WriteTo.File(builder.Configuration["LogPath"], rollingInterval: RollingInterval.Day) // Log to a file
    #pragma warning restore CS8604
    .CreateLogger();

// Retrieve all network interfaces
var allNetworkInterfaces = NetworkInterface.GetAllNetworkInterfaces();

// Find the Ethernet interface
var ethernetInterface = allNetworkInterfaces.FirstOrDefault(ni => ni.Name == "Ethernet" && ni.OperationalStatus == OperationalStatus.Up);
// create an IP address object with a default value 127.0.0.1
IPAddress ipAddress = IPAddress.Parse("127.0.0.1");

if (ethernetInterface != null)
{
    // Get the IP address information
    var ipProperties = ethernetInterface.GetIPProperties();
    var ipAddressInformation = ipProperties.UnicastAddresses.FirstOrDefault(ip => ip.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork);

    if (ipAddressInformation != null)
    {
        Console.WriteLine($"IP Address: {ipAddressInformation.Address}");
        ipAddress = ipAddressInformation.Address;
    }
    else
    {
        Console.WriteLine("IP Address not found for Ethernet interface.");
        Environment.Exit(1);
    }
}
else
{
    Console.WriteLine("Ethernet interface not found.");
    Environment.Exit(1);
}

// Specify the URLs to listen on
builder.WebHost.UseUrls("http://localhost:5000", "http://localhost:8000", $"http://{ipAddress}:8000");

// Add services to the container.
builder.Services.AddRazorPages();

builder.Host.UseSerilog();

builder.Services.AddControllersWithViews(); // Add MVC services

var app = builder.Build();

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
    app.UseHsts();
}

app.UseHttpsRedirection();
app.UseStaticFiles();

app.UseRouting();

app.UseAuthorization();

app.MapRazorPages();
app.MapControllerRoute( // Map controller routes
    name: "default",
    pattern: "{controller=Home}/{action=Index}/{id?}");

app.Run();