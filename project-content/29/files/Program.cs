using NAudio.CoreAudioApi;
using NPSMLib;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Runtime.Versioning;
using System.Text;

class MediaControl
{
    private NowPlayingSessionManager sessionManager;

    public MediaControl()
    {
        sessionManager = new NowPlayingSessionManager();
    }

    private void SendCommand(MediaPlaybackCommands command)
    {
        var session = sessionManager.CurrentSession;
        if (session == null)
        {
            Console.WriteLine("No media playing");
        }else{
            var mediaPlaybackDataSource = session.ActivateMediaPlaybackDataSource();
            mediaPlaybackDataSource.SendMediaPlaybackCommand(command);
        
        }
    }

    public void PlayPause()
    {
        SendCommand(MediaPlaybackCommands.PlayPauseToggle);
        
    }
    public void PauseMedia()
    {
        SendCommand(MediaPlaybackCommands.Pause);

    }

    public void PlayMedia()
    {
        SendCommand(MediaPlaybackCommands.Play);
    }

    public void NextMedia()
    {
        SendCommand(MediaPlaybackCommands.Next);
    }

    public void PreviousMedia()
    {
        SendCommand(MediaPlaybackCommands.Previous);
    }
    public void FastForwardMedia()
    {
        SendCommand(MediaPlaybackCommands.FastForward);
    }

    public void RewindMedia()
    {
        SendCommand(MediaPlaybackCommands.Rewind);
    }
}

public class MicrophoneController
{
    [SupportedOSPlatform("windows")]
    private static MMDevice GetDevice()
    {
        var device = new MMDeviceEnumerator().EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active).FirstOrDefault(d => d.DeviceFriendlyName == "DroidCam Virtual Audio"); ;
        if (device == null)
        {
            Console.WriteLine("Microphone not found");
            Environment.Exit(-1);
        }
        return device;
    }


    [SupportedOSPlatform("windows")]
    public static void ToggleMicrophoneMute(bool toggle)
    {
        var device = GetDevice();
        device.AudioEndpointVolume.Mute = toggle;
    }


    [SupportedOSPlatform("windows")]
    public static bool IsMicrophoneMuted()
    {
        var device = GetDevice();
        return device.AudioEndpointVolume.Mute;
    }
}

public class VCableVolumeController
{

    public static float GetApplicationVolume(string appName)
    {
        using (var enumerator = new MMDeviceEnumerator())
        {
            using (var device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia))
            {
                var sessions = device.AudioSessionManager.Sessions;
                for (int i = 0; i < sessions.Count; i++)
                {
                    var session = sessions[i];
                    if (session.GetProcessID == 0) continue; // Skip system sounds
                    var displayName = session.DisplayName;
                    if (displayName != appName) continue;

                    return session.SimpleAudioVolume.Volume;
                }
            }
        }
        return 0;
    }
    public static void SetApplicationVolume(string appName, float volume)
    {
        using (var enumerator = new MMDeviceEnumerator())
        {
            // MessageBox with the audio endpoint device names
            //MessageBox.Show(string.Join("\n", enumerator.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active).Select(x => x.FriendlyName + " " + x.DeviceFriendlyName)));
            // Get the audio endpoint device with DeviceFriendlyname = "VB-Audio Hi-Fi Cable"
            using (var device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia))
            {
                var sessions = device.AudioSessionManager.Sessions;
                for (int i = 0; i < sessions.Count; i++)
                {
                    var session = sessions[i];
                    if (session.GetProcessID == 0) continue; // Skip system sounds
                    var displayName = session.DisplayName;
                    if (displayName != "Hi-Fi Cable Output (VB-Audio Hi-Fi Cable)") continue;

                    var process = System.Diagnostics.Process.GetProcessById((int)session.GetProcessID);
                    session.SimpleAudioVolume.Volume = volume; // Volume is a scalar between 0.0 and 1.0
                                                               //Console.WriteLine($"Volume for {appName} set to {volume * 100}%");
                    break;

                }
            }
        }
    }
}

class TcpServer
{
    public static void Main()
    {
        TcpListener? server = null;
        try
        {
            Int32 port = 5000;
            IPAddress localAddr = IPAddress.Parse("192.168.1.4");

            server = new TcpListener(localAddr, port);

            server.Start();
            Console.WriteLine("Start server.");

            while (true)
            {
                try
                {
                    TcpClient client = server.AcceptTcpClient();
                    NetworkStream stream = client.GetStream();

                    byte[] bytes = new byte[256];
                    int i;

                    while ((i = stream.Read(bytes, 0, bytes.Length)) != 0)
                    {
                        string command = Encoding.ASCII.GetString(bytes, 0, i);
                        Console.WriteLine("Received: {0}", command);

                        switch (command)
                        {
                            case "play":
                                new MediaControl().PlayMedia();
                                break;
                            case "pause":
                                new MediaControl().PauseMedia();
                                break;
                            case "play/pause":
                                new MediaControl().PlayPause();
                                break;
                            case "next":
                                new MediaControl().NextMedia();
                                break;
                            case "previous":
                                new MediaControl().PreviousMedia();
                                break;
                            case "fastforward":
                                new MediaControl().FastForwardMedia();
                                break;
                            case "rewind":
                                new MediaControl().RewindMedia();
                                break;
                                
                            case "toggle_microphone":
                                new Thread(() =>
                                {
                                    new MediaControl().PauseMedia();
                                    VCableVolumeController.SetApplicationVolume("Hi-Fi Cable Output (VB-Audio Hi-Fi Cable)", 0f);
                                    Thread.Sleep(1000);
                                    MicrophoneController.ToggleMicrophoneMute(false);
                                }).Start();
                                break;
                            case "toggle_music":
                                new Thread(() =>
                                {
                                    MicrophoneController.ToggleMicrophoneMute(true);
                                    Thread.Sleep(1000);
                                    VCableVolumeController.SetApplicationVolume("Hi-Fi Cable Output (VB-Audio Hi-Fi Cable)", 1.0f);
                                }).Start();
                                break;
                            case "status":
                                string status = GetStatus();
                                byte[] statusBytes = Encoding.ASCII.GetBytes(status);
                                stream.Write(statusBytes, 0, statusBytes.Length);
                                break;
                        }

                        client.Close();
                    }
                }
                catch (System.ObjectDisposedException)
                { }
                catch (Exception e)
                {
                    Console.WriteLine(e);
                }

            }
        }
        catch (SocketException e)
        {
            Console.WriteLine("SocketException: {0}", e);
        }
        finally
        {
            server?.Stop();
        }
    }

    private static string GetStatus()
    {
        bool isMicrophoneMuted = MicrophoneController.IsMicrophoneMuted();
        float hiFiCableVolume = VCableVolumeController.GetApplicationVolume("Hi-Fi Cable Output (VB-Audio Hi-Fi Cable)");

        if (isMicrophoneMuted && hiFiCableVolume == 1.0f)
        {
            return "Music";
        }
        else if (isMicrophoneMuted && hiFiCableVolume == 0f)
        {
            return "No source"; // should not 
        }
        else if (!isMicrophoneMuted && hiFiCableVolume == 1.0f)
        {
            return "Mic and Music";
        }
        else if (!isMicrophoneMuted && hiFiCableVolume == 0f)
        {
            return "Microphone";
        }
        return "";
    }
}
