using NAudio.CoreAudioApi;
using System.Diagnostics;
using System.Linq;
using System.Windows.Forms;

namespace ShowMicVolume
{
    public partial class MainForm : Form
    {
        private readonly MMDevice VBCableDevice;
        private readonly AudioSessionControl MicrophoneDeviceSession;
        private readonly System.Windows.Forms.Timer timer;
        private readonly float minLevel = 3.0517578E-05f; // Set min level manually
        private float maxLevel = 0.985f; // Set max level manually

        public MainForm()
        {
            InitializeComponent();

            VBCableDevice = MMFinder.GetMMDevice("VB-Audio Hi-Fi Cable", DataFlow.Capture) ?? throw new Exception("VBCableDevice not found");

            MicrophoneDeviceSession = MMFinder.GetAudioSessionControlByAppName(
                (MMFinder.GetMMDevice("VB-Audio Hi-Fi Cable", DataFlow.Render) ?? throw new Exception("VBCableDevice not found")),
                "Microphone (WO Mic Device)"
            ) ?? throw new Exception("Microphone not found");

            timer = new System.Windows.Forms.Timer { Interval = 20 }; // Update 100 times per second
            timer.Tick += Timer_Tick;
            timer.Start();
        }

        private void MainForm_Load(object sender, EventArgs e)
        {
            // Center the progress bars
            progressBar.Location = new Point((this.ClientSize.Width / 2 - progressBar.Width) - 10, 10);
            progressBar2.Location = new Point((this.ClientSize.Width / 2 + 10), 10);

            // Position the labels below the progress bars
            label1.Location = new Point(progressBar.Right - label1.Width, progressBar.Bottom + 10);
            label2.Location = new Point(progressBar2.Left, progressBar2.Bottom + 10);

            // Position the status label below the main labels
            statusLabel.Location = new Point(Math.Abs(this.ClientSize.Width - statusLabel.Width) / 2, label1.Bottom + 20);
        }

        private void Timer_Tick(object sender, EventArgs e)
        {
            // Update progress bar for VBCableDevice
            float level1 = VBCableDevice.AudioMeterInformation.MasterPeakValue;
            if (level1 > maxLevel)
            {
                maxLevel = level1;
            }
            float normalizedLevel1 = (level1 - minLevel) / (maxLevel - minLevel);
            int percentage1 = Math.Min(100, Math.Max(0, (int)(normalizedLevel1 * 100)));
            // Debug.WriteLine($"{VBCableDevice.AudioMeterInformation.MasterPeakValue}");
            progressBar.Value = percentage1;
            label1.Text = $"VBCableDevice: {percentage1}%";

            // Update progress bar for Microphone
            float level2 = GetMicrophoneLevel();
            if (level2 > maxLevel)
            {
                maxLevel = level2;
            }
            float normalizedLevel2 = (level2 - minLevel) / (maxLevel - minLevel);
            int percentage2 = Math.Min(100, Math.Max(0, (int)(normalizedLevel2 * 100)));

            progressBar2.Value = percentage2;
            label2.Text = $"Microphone: {percentage2}%";

            // Update status label based on Microphone status
            if (IsMicMuted())
            {
                statusLabel.Text = "Musique";
                label2.Visible = false;
                progressBar2.Visible = false;
            }
            else
            {
                statusLabel.Text = "Microphone";
                label2.Visible = true;
                progressBar2.Visible = true;
            }

            statusLabel.Location = new Point(Math.Abs(this.ClientSize.Width - statusLabel.Width) / 2, label1.Bottom + 20);
            label1.Location = new Point(progressBar.Right - label1.Width, progressBar.Bottom + 10);

            // debuglabel.Text = "Max level = " + maxLevel;
        }

        private float GetMicrophoneLevel()
        {

            return MicrophoneDeviceSession.AudioMeterInformation.MasterPeakValue;
        }

        private bool IsMicMuted()
        {
            return MicrophoneDeviceSession.SimpleAudioVolume.Mute;
        }
    }

    public static class MMFinder
    {
        public static MMDevice? GetMMDevice(string deviceName, DataFlow dataFlow = DataFlow.Render)
        {
            using var enumerator = new MMDeviceEnumerator();
            for (int i = 0; i < enumerator.EnumerateAudioEndPoints(dataFlow, DeviceState.Active).Count; i++)
            {
                var device = enumerator.EnumerateAudioEndPoints(dataFlow, DeviceState.Active)[i];
                if (device.DeviceFriendlyName == deviceName)
                {
                    return device;
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
}
