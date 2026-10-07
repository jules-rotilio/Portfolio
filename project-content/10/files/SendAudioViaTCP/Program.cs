using System;
using System.Net.Sockets;
using NAudio.Wave;

class Program
{
    static void Main()
    {
        var waveIn = new WaveInEvent
        {
            WaveFormat = new WaveFormat(88200, 16, 2),
            DeviceNumber = 0,
        };

        using TcpClient client = new TcpClient("192.0.2.20", 5000);
        Console.WriteLine("Connected to the receiver.");
        using NetworkStream stream = client.GetStream();

        waveIn.DataAvailable += (sender, e) =>
        {
            stream.Write(e.Buffer, 0, e.BytesRecorded);
        };

        waveIn.StartRecording();

        Console.WriteLine("Recording... Press any key to stop.");
        Console.ReadKey();
    }
}
