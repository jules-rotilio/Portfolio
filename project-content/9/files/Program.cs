using System;
using System.Net.Sockets;
using System.Net.Mail;
using System.Threading.Tasks;

class Program
{
    static readonly string[] hostsToTest = { "mail.rotilio.fr" };
    static readonly int[] portsToTest = { 25, 587, 993, 443, 80 };
    static readonly (string host, int port)[] fallbackHosts = {
        ("1.1.1.1", 443), // Cloudflare
        ("8.8.8.8", 443)  // Google
    };

    static async Task<bool> TestPortAsync(string host, int port, int retries = 3, int timeoutMs = 4000)
    {
        for (int i = 0; i < retries; i++)
        {
            using (var client = new TcpClient())
            {
                try
                {
                    var connectTask = client.ConnectAsync(host, port);
                    if (await Task.WhenAny(connectTask, Task.Delay(timeoutMs)) == connectTask && client.Connected)
                        return true;
                }
                catch { }
            }
            await Task.Delay(200); // Petite pause entre les essais
        }
        return false;
    }

    static async Task<bool> TestAllPortsAsync()
    {
        foreach (var port in portsToTest)
        {
            bool ok = await TestPortAsync(hostsToTest[0], port);
            if (!ok)
                return false;
        }
        return true;
    }

    static async Task<bool> TestFallbackAsync()
    {
        foreach (var (host, port) in fallbackHosts)
        {
            if (await TestPortAsync(host, port))
                return true;
        }
        return false;
    }

    static void SendGmailAlert()
    {
        var fromAndTo = "you@example.com";
        var subject = "Alerte : Tous les ports du serveur mail sont inaccessibles";
        var body = "Tous les ports testés sur mail.rotilio.fr sont inaccessibles.";

        using (var client = new SmtpClient("smtp.gmail.com", 587))
        {
            client.EnableSsl = true;
            client.Credentials = new System.Net.NetworkCredential(fromAndTo, "<REDACTED>");
            var mail = new MailMessage(fromAndTo, fromAndTo, subject, body);
            client.Send(mail);
        }
    }

    static async Task Main()
    {
        while (true)
        {
            uint allPortsOk = 0b_11111;
            Console.WriteLine(allPortsOk.ToString("X2") + " - Test des ports du serveur mail...");
            for (int i = 0; i < portsToTest.Length; i++)
            {
                bool ok = await TestPortAsync(hostsToTest[0], portsToTest[i]);
                if (!ok)
                {
                    allPortsOk &= ~(1u << i); // Met le bit correspondant à 0 si le port n'est pas accessible
                    Console.WriteLine($"Port {portsToTest[i]} ({hostsToTest[0]}) : Inaccessible");
                }
            }
            Console.WriteLine(allPortsOk.ToString("X2") + " - Résultat du test des ports du serveur mail.");

            if (allPortsOk == 0b_00000) // Tous les ports sont inaccessibles
            {
                Console.WriteLine("Tous les ports du serveur mail sont inaccessibles. Tentative de connexion aux serveurs de secours...");
                while (!await TestFallbackAsync())
                { }
                SendGmailAlert();
                Console.WriteLine("Tous les ports du serveur mail sont inaccessibles. Alerte envoyée par email.");
            }

            await Task.Delay(TimeSpan.FromMinutes(15)); // Pause entre les boucles
        }
    }
}
