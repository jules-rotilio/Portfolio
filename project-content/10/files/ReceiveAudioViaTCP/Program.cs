using System;
using System.Net;
using System.Net.Sockets;
using NAudio.Wave;
using NAudio;

class Program
{
    static void Main(string[] args)
    {
        bool recordToFile = args.Length > 0 && bool.TryParse(args[0], out bool result) && result;
        for (int i = 0; i < WaveOut.DeviceCount; i++)
        {
            string s = $"Device {i}: {WaveOut.GetCapabilities(i).ProductName}";
            Console.WriteLine(s);
        }

        // Demander à l'utilisateur de sélectionner un périphérique
        Console.Write("Select output device (default is 0): ");
        int deviceNumber = 0;
        if (int.TryParse(Console.ReadLine(), out int selectedDevice))
        {
            deviceNumber = selectedDevice;
        }

        TcpListener listener = new(IPAddress.Any, 5000);
        listener.Start();

        Console.WriteLine("Waiting for connection...");

        try
        {
            using TcpClient client = listener.AcceptTcpClient();
            Console.WriteLine("Connection established with sender.");
            using NetworkStream stream = client.GetStream();
            using WaveOutEvent waveOut = new() { DeviceNumber = deviceNumber };
            var waveProvider = new BufferedWaveProvider(new WaveFormat(88200, 16, 2));
            waveOut.Init(waveProvider);
            waveOut.Play();

            WaveFileWriter waveFileWriter = null;
            if (recordToFile)
            {
                waveFileWriter = new WaveFileWriter("recordedAudio.wav", waveProvider.WaveFormat);
                Console.WriteLine("Recording audio to file: recordedAudio.wav");
            }

            byte[] buffer = new byte[1024];
            int bytesRead;

            while ((bytesRead = stream.Read(buffer, 0, buffer.Length)) > 0)
            {
                waveProvider.AddSamples(buffer, 0, bytesRead);
                waveFileWriter?.Write(buffer, 0, bytesRead);
            }

            waveFileWriter?.Dispose();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"An error occurred: {ex.Message}");
        }
    }
}
