using Newtonsoft.Json;
using SharpPcap;
using PacketDotNet;
using System.Text;

namespace honeypot
{
    public class PacketSniffer : IDisposable
    {
        private readonly object _lock = new();

        private readonly Parameters _parameters;
        private readonly StreamWriter _fileWriter;

        public PacketSniffer(Parameters parameters)
        {
            _parameters = parameters;
            _fileWriter = new StreamWriter(_parameters.LogFilePath, append: true, encoding: Encoding.UTF8);
        }
        public void AddToFile(string content)
        {
            lock (_lock)
            {
                _fileWriter.WriteLine(content);
                _fileWriter.Flush();
            }
        }




        public void StartSniffing()
        {
            var devices = CaptureDeviceList.Instance;
            if (devices.Count < 1)
            {
                Console.WriteLine("No devices were found on this machine");
                return;
            }

            for (int i = 0; i != devices.Count; ++i)
            {
                Console.WriteLine("{0}) {1}", i, devices[i].Description);
            }

            ICaptureDevice? device = null;
            do
            {
                Console.WriteLine("Choose a device to capture: ");
                if (!int.TryParse(Console.ReadLine(), out int deviceIndex))
                {
                    Console.WriteLine("Invalid input. Please enter a number.");
                    continue;
                }

                device = devices[deviceIndex];
            } while (device == null);

            Console.Clear();
            device.Open(DeviceModes.Promiscuous);

            device.OnPacketArrival += _parameters.Ports.Count > 1
                ? new PacketArrivalEventHandler(Device_OnPacketArrival_Port)
                : new PacketArrivalEventHandler(Device_OnPacketArrival_Ports);

            device.StartCapture();
        }

        private void Device_OnPacketArrival_Port(object sender, PacketCapture e)
        {
            ProcessPacket(e, 22);
        }

        private void Device_OnPacketArrival_Ports(object sender, PacketCapture e)
        {
            var ipPacket = ExtractIpPacket(e);
            var tcpPacket = ExtractTcpPacket(ipPacket);
            if (tcpPacket != null && _parameters.Ports.Contains(tcpPacket.DestinationPort))
            {
                ProcessPacket(e, tcpPacket.DestinationPort);
            }
        }

        private void ProcessPacket(PacketCapture e, int port)
        {
            var ipPacket = ExtractIpPacket(e);
            var tcpPacket = ExtractTcpPacket(ipPacket);

            if (tcpPacket != null && tcpPacket.DestinationPort == port)
            {
                var content = $"Source IP: {ipPacket.SourceAddress}\n" +
                              $"Destination Port: {tcpPacket.DestinationPort}\n" +
                              $"Protocol: {ipPacket.Protocol}\n";
                Console.WriteLine(content);
                AddToFile(content);
            }
        }

        private static IPPacket ExtractIpPacket(PacketCapture p)
        {
            var rawPacket = p.GetPacket();
            return Packet.ParsePacket(rawPacket.LinkLayerType, rawPacket.Data).Extract<IPPacket>();
        }
        private static IcmpV4Packet ExtractIcmpPacket(IPPacket p)
        {
            return p.Extract<IcmpV4Packet>();
        }

        private static TcpPacket ExtractTcpPacket(IPPacket p)
        {
            return p.Extract<TcpPacket>();
        }

        private static UdpPacket ExtractUdpPacket(IPPacket p)
        {
            return p.Extract<UdpPacket>();
        }

        public void Dispose()
        {
            // Dispose StreamWriter
            _fileWriter?.Dispose();

            // Dispose other unmanaged resources here

            // Suppress finalization
            GC.SuppressFinalize(this);
        }

    }


    public class Parameters
    {
        public string LogFilePath { get; set; } = string.Empty;
        public int Port { get; set; }
        public string Interface { get; set; } = string.Empty;
        public List<int> Ports { get; set; } = [];
    }


    public class Program
    {
        static bool _continue = true;
        public static void Main()
        {
            var parametersJson = File.ReadAllText("parameters.json");
            var parameters = JsonConvert.DeserializeObject<Parameters>(parametersJson);
            if (parameters == null)
            {
                Console.WriteLine("Invalid parameters");
                Console.WriteLine(@"Please make sure the parameters.json file is in the same directory as the executable");
                Console.WriteLine(@"The file should have the following format:"
                                    + @"{""LogFilePath"":""C:\path\to\log.txt"",""Port"":80,""Interface"":""eth0"",""Ports"":[80,443]}");
                Console.WriteLine("Press any key to exit");
                Console.ReadKey();
                return;
            }

            if (parameters.Ports.Count == 0)
            {
                if (parameters.Port != 0)
                    Console.WriteLine(parameters.Port);
                else
                    Console.WriteLine("No ports specified");
            }
            else
            {

                for (int i = 0; i < parameters.Ports.Count; i++)
                    Console.Write(parameters.Ports[i] + " ");

                Console.WriteLine();
            }
            Console.WriteLine(parameters.LogFilePath);
            var sniffer = new PacketSniffer(parameters);
            sniffer.StartSniffing();
            Console.CancelKeyPress += (sender, e) =>
            {
                e.Cancel = true; // Cela empêche l'application de se terminer immédiatement
                _continue = false;
            };
            while (_continue)
            {
                if (Console.ReadLine() == "exit") break;
            }
        }
    }
}