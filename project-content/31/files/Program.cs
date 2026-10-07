using NAudio.CoreAudioApi;
using NPSMLib;
using System.Runtime.Versioning;
using System.Windows.Forms;

namespace ToggleMicrophoneSoundboard
{
    public class MMFinder
    {
        public static MMDevice? GetMMDevice(string deviceName, DataFlow dataFlow = DataFlow.Render)
        {
            using (var enumerator = new MMDeviceEnumerator())
            {
                for (int i = 0; i < enumerator.EnumerateAudioEndPoints(dataFlow, DeviceState.Active).Count; i++)
                {
                    var device = enumerator.EnumerateAudioEndPoints(dataFlow, DeviceState.Active)[i];
                    if (device.DeviceFriendlyName == deviceName)
                    {
                        return device;
                    }
                }
            }
            return null;
        }

        public static AudioSessionControl? GetAudioSessionControlByProcessName(MMDevice mMDevice, string processName)
        {
            var sessions = mMDevice.AudioSessionManager.Sessions;
            for (int i = 0; i < sessions.Count; i++)
            {
                var session = sessions[i];
                if (session.GetProcessID == 0) continue; // Skip system sounds
                uint pid = session.GetProcessID;
                var process = System.Diagnostics.Process.GetProcessById((int)pid);
                if (process.ProcessName == processName)
                {
                    return session;
                }
            }
            return null;
        }

        public static AudioSessionControl? GetAudioSessionControlByMute(MMDevice mMDevice)
        {
            var sessions = mMDevice.AudioSessionManager.Sessions;
            for (int i = 0; i < sessions.Count; i++)
            {
                var session = sessions[i];
                if (session.GetProcessID == 0) continue; // Skip system sounds
                if (session.SimpleAudioVolume.Mute)
                {
                    return session;
                }
            }
            return null;
        }

        public static AudioSessionControl? GetAudioSessionControlByAppName(MMDevice mMDevice, string appName)
        {
            var sessions = mMDevice.AudioSessionManager.Sessions;

            for (int i = 0; i < sessions.Count; i++)
            {
                var session = sessions[i];
                if (session.GetProcessID == 0) continue; // Skip system sounds
                var displayName = session.DisplayName;
                if (displayName != appName) continue;
                return session;
            }
            return null;
        }
    }
    public class VCableVolumeController
    {

        public static void SetApplicationVolume(string appName, float volume)
        {
            var device = MMFinder.GetMMDevice("WH-1000XM5");

            if (device == null)
            {
                Console.WriteLine("Device not found");
                return;
            }

            var session = MMFinder.GetAudioSessionControlByAppName(device, appName);

            if (session == null)
            {
                Console.WriteLine("Session not found");
                return;
            }

            session.SimpleAudioVolume.Volume = volume; // Volume is a scalar between 0.0 and 1.0

        }

        public static float GetApplicationVolume(string appName)
        {
            var device = MMFinder.GetMMDevice("WH-1000XM5");

            if (device == null)
            {
                Console.WriteLine("Device not found");
                return 0;
            }

            var session = MMFinder.GetAudioSessionControlByAppName(device, appName);

            if (session == null)
            {
                Console.WriteLine("Session not found");
                return 0;
            }

            return session.SimpleAudioVolume.Volume;
        }
    }

    public class MicrophoneController
    {
        [SupportedOSPlatform("windows")]
        public static void ToggleMicrophoneMute(bool toggle)
        {
            var device = MMFinder.GetMMDevice("VB-Audio Hi-Fi Cable", DataFlow.Render);

            if (device == null)
            {
                Console.WriteLine("Device not found");
                return;
            }

            var session = MMFinder.GetAudioSessionControlByAppName(device, "Microphone (WO Mic Device)");

            if (session == null)
            {
                Console.WriteLine("Session not found");
                return;
            }

            session.SimpleAudioVolume.Mute = toggle;
        }
    }

    public class MediaControl
    {
        private NowPlayingSessionManager sessionManager;

        public MediaControl()
        {
            sessionManager = new NowPlayingSessionManager();
        }

        public void PauseMedia()
        {
            var session = sessionManager.CurrentSession;
            if (session == null)
            {
                Console.WriteLine("No media playing");
                return;
            }
            var mediaPlaybackDataSource = session.ActivateMediaPlaybackDataSource();
            mediaPlaybackDataSource.SendMediaPlaybackCommand(MediaPlaybackCommands.Pause);

        }
    }


    static class Program
    {
        [STAThread]
        static void Main()
        {

            VCableVolumeController controller = new ();
            string appName = "Hi-Fi Cable Output (VB-Audio Hi-Fi Cable)";

            var volume = VCableVolumeController.GetApplicationVolume(appName);
            switch (volume)
            {
                case 0:
                    MicrophoneController.ToggleMicrophoneMute(true);
                    Console.Beep(400, 100);
                    Console.Beep(500, 100);
                    Console.Beep(600, 100);
                    VCableVolumeController.SetApplicationVolume(appName, 1f); // Set volume to 100%
                    break;
                case 1:
                    VCableVolumeController.SetApplicationVolume(appName, 0f); // Mute
                    new MediaControl().PauseMedia();
                    MicrophoneController.ToggleMicrophoneMute(false);
                    Console.Beep(300, 100);
                    break;
                default:
                    VCableVolumeController.SetApplicationVolume(appName, 0f); // Mute
                    new MediaControl().PauseMedia();
                    MicrophoneController.ToggleMicrophoneMute(false);
                    Console.Beep(300, 100);
                    break;
            }
        }
    }
}