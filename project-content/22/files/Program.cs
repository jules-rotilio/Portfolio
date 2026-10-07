using NAudio.CoreAudioApi;
using System.Data;
using System.Media;
using System.Runtime.Versioning;

namespace Program
{
    class Program
    {
        [SupportedOSPlatform("windows")]
        private static void DisplayMicrophoneNames()
        {
            var device = (new MMDeviceEnumerator()).EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active).FirstOrDefault(d => d.DeviceFriendlyName == "Pro 9000"); ;
            if (device == null)
            {
                Console.WriteLine("Microphone not found");
                Environment.Exit(-1);
            }
            if (device.AudioEndpointVolume.Mute)
            {
                Console.WriteLine("Microphone is muted");
                device.AudioEndpointVolume.Mute = false;
                Console.WriteLine("Microphone is now unmuted");
                Console.Beep(440, 100);
            }
            else
            {
                Console.WriteLine("Microphone is not muted");
                device.AudioEndpointVolume.Mute = true;
                Console.WriteLine("Microphone is now muted");
                Console.Beep(440, 100);
                System.Threading.Thread.Sleep(100);
                Console.Beep(440, 100);
            }
            Environment.Exit(0);

        }
        static void Main(string[] args)
        {
#pragma warning disable CA1416
            DisplayMicrophoneNames();
#pragma warning restore CA1416

        }
    }
}