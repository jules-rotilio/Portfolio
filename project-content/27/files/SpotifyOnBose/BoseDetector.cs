using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Xml;
using System.Net;
using System.Diagnostics;

namespace SpotifyAlarmClockOnBose
{
    internal class BoseDetector
    {

        private static readonly HttpClient httpClient;

        static BoseDetector()
        {
            // Configurer SocketsHttpHandler pour remplacer ServicePointManager
            var handler = new SocketsHttpHandler
            {
                MaxConnectionsPerServer = 100, // Limite des connexions simultanées par serveur
                PooledConnectionLifetime = TimeSpan.FromMinutes(5), // Durée de vie des connexions dans le pool
                PooledConnectionIdleTimeout = TimeSpan.FromMinutes(1), // Durée d'inactivité avant qu'une connexion soit supprimée
                ConnectTimeout = TimeSpan.FromMilliseconds(1500) // Timeout pour établir une connexion
            };

            httpClient = new HttpClient(handler)
            {
                Timeout = TimeSpan.FromMilliseconds(1500) // Timeout global pour les requêtes
            };
        }

        public async static Task<BoseSpeaker> GetBoseSpeaker()
        {
            //find the device on the network
            string ip = await FindDevice();
            if (string.IsNullOrEmpty(ip))
            {
                //if no device is found, return null
                throw new BoseNotFoundException("No Bose device found on the network.");
            }
            else
            {
                //create a new BoseSpeaker object with the ip address
                string url = $"http://{ip}:8090";
                BoseSpeaker bose = new BoseSpeaker(url);
                return bose;
            }
        }

        private async static Task<string> FindDevice()
        {
            if (!CanScan())
            {
                return string.Empty;
            }

            var ipList = Enumerable.Range(2, 251).Select(i => $"192.168.1.{i}").ToList();
            var semaphore = new SemaphoreSlim(10); // Limiter à 10 requêtes simultanées
            var tasks = new List<Task<string>>();

            foreach (var ip in ipList)
            {
                await semaphore.WaitAsync();
                tasks.Add(Task.Run(async () =>
                {
                    try
                    {
                        return await CheckDevice(ip);
                    }
                    finally
                    {
                        semaphore.Release();
                    }
                }));
            }

            var results = await Task.WhenAll(tasks);
            return results.FirstOrDefault(ip => !string.IsNullOrEmpty(ip)) ?? string.Empty;
        }

        private static bool found = false;
        private async static Task<string> CheckDevice(string ip)
        {
            if (found)
            {
                return string.Empty;
            }
            try
            {
                // Envoyer une requête GET directement
                var response = await httpClient.GetAsync($"http://{ip}:8090/info");
                if (response.IsSuccessStatusCode)
                {
                    Debug.WriteLine($"Checking {ip} success");
                    var xml = await response.Content.ReadAsStringAsync();
                    XmlDocument doc = new XmlDocument();
                    doc.LoadXml(xml);

                    // Vérifier le nom de l'appareil
                    var nameNode = doc.SelectSingleNode("//info/name");
                    if (nameNode != null)
                    {
                        string deviceName = nameNode.InnerText;
                        string boseName = Configuration.GetInstance().SpeakerName;
                        if (deviceName == boseName)
                        {
                            found = true;
                            return ip;
                        }
                    }
                }
            }
            catch (System.Threading.Tasks.TaskCanceledException /*TCex*/)
            {
                //Debug.WriteLine($"Error checking {ip}: {TCex.Message}");
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Error checking {ip}: {ex.Message}");
                Debug.WriteLine(ex.GetType());
            }

            return string.Empty;
        }

        private static bool CanScan()
        {
            //get ip network:
            string[] ipAddresses = System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces()
                .SelectMany(n => n.GetIPProperties().UnicastAddresses)
                .Where(ip => ip.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
                .Select(ip => ip.Address.ToString())
                .ToArray();

            //if ipAddresses has an ip address that starts with 192.168.1. then return true
            foreach (string ip in ipAddresses)
            {
                if (ip.StartsWith("192.168.1."))
                {
                    return true;
                }
            }

            return false;
        }
    }
}