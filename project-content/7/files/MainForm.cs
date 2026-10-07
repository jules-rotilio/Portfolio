using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Net.Http;
using System.Threading;
using NAudio.CoreAudioApi;

namespace scp_sl_v2
{
    public partial class MainForm : Form
    {
        // --- Added for audio monitoring (from ShowMicVolume) ---
        private MMDevice VBCableDevice;
        private AudioSessionControl MicrophoneDeviceSession;
        private readonly System.Windows.Forms.Timer audioTimer;
        private readonly float minLevel = 3.0517578E-05f;
        private float maxLevel = 0.985f;
        // --------------------------------------------------------

        public MainForm()
        {
            InitializeComponent();

            // keep existing window constraints
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;

            // start the UI-resize thread (existing behavior)
            new Thread(() =>
            {
                while (!IsDisposed)
                {
                    Thread.Sleep(1000);
                    if (IsHandleCreated)
                    {
                        Invoke((MethodInvoker)delegate
                        {
                            Width = 305;
                            Height = 1039;
                        });
                    }
                }
            }).Start();

            // Initialize audio monitoring (best-effort; failures are non-fatal)
            try
            {
                // Try find virtual cable (capture) and microphone session (on render device)
                VBCableDevice = MMFinder.GetMMDevice("VB-Audio Hi-Fi Cable", DataFlow.Capture);
                var renderVBCable = MMFinder.GetMMDevice("VB-Audio Hi-Fi Cable", DataFlow.Render);
                if (renderVBCable != null)
                {
                    // App name used previously in the other project
                    MicrophoneDeviceSession = MMFinder.GetAudioSessionControlByAppName(renderVBCable, "Microphone (WO Mic Device)");
                }

                // If devices found, start timer to update UI
                audioTimer = new System.Windows.Forms.Timer { Interval = 20 }; // 50 Hz (20 ms)
                audioTimer.Tick += AudioTimer_Tick;

                // If devices were located, start updates; otherwise still start timer but it will be harmless
                audioTimer.Start();
            }
            catch
            {
                // Never throw from constructor for missing audio hardware — keep app usable.
            }
        }

        private void AudioTimer_Tick(object sender, EventArgs e)
        {
            // Update virtual cable meter if device available
            if (VBCableDevice != null && virtualCableVolumeMeter != null)
            {
                try
                {
                    float level1 = VBCableDevice.AudioMeterInformation.MasterPeakValue;
                    if (level1 > maxLevel) maxLevel = level1;
                    float normalized1 = (level1 - minLevel) / Math.Max(1e-6f, (maxLevel - minLevel));
                    int pct1 = Math.Min(100, Math.Max(0, (int)(normalized1 * 100)));
                    // Update VolumeMeter visual amplitude and label text
                    virtualCableVolumeMeter.Amplitude = level1;
                }
                catch { /* swallow per-tick errors */ }
            }

            // Update microphone meter if session available
            if (MicrophoneDeviceSession != null && microphoneVolumeMeter != null)
            {
                try
                {
                    float level2 = MicrophoneDeviceSession.AudioMeterInformation.MasterPeakValue;
                    if (level2 > maxLevel) maxLevel = level2;
                    float normalized2 = (level2 - minLevel) / Math.Max(1e-6f, (maxLevel - minLevel));
                    int pct2 = Math.Min(100, Math.Max(0, (int)(normalized2 * 100)));
                    microphoneVolumeMeter.Amplitude = level2;

                    // If the session exposes mute status, reflect it by dimming label (non-intrusive)
                    try
                    {
                        bool muted = MicrophoneDeviceSession.SimpleAudioVolume.Mute;
                        microphoneLabel.Visible = !muted;
                        microphoneVolumeMeter.Visible = !muted;
                    }
                    catch { }
                }
                catch { /* swallow per-tick errors */ }
            }
        }

        public void UpdatePageLabel(string text)
        {
            if (IsHandleCreated)
            {
                Invoke((MethodInvoker)delegate
                {
                    labelPage2.Text = text;
                });
            }
        }

        public void UpdateVolumeTrackbar(int value)
        {
            if (IsHandleCreated)
            {
                Invoke((MethodInvoker)delegate
                {
                    trackBar1.Value = value;
                });
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            using (HttpClient client = new HttpClient())
            {
                try { client.GetAsync("http://127.0.0.1:8000/shutdown").Wait(1000); }
                catch { }
            }

            try
            {
                audioTimer?.Stop();
                audioTimer?.Dispose();
            }
            catch { }

            try
            {
                MicrophoneDeviceSession?.Dispose();
            }
            catch { }

            try
            {
                VBCableDevice?.Dispose();
            }
            catch { }

            base.OnFormClosing(e);
            Environment.Exit(0);
        }
        public void UpdateButtons(Config conf)
        {
            if (!IsHandleCreated || conf == null || conf.Keys == null)
                return;

            Invoke((MethodInvoker)delegate
            {
                button1.Text    = conf.Keys.TryGetValue("1", out var v1) ? v1.Split("\\").Last() : "Non défini";
                button2.Text    = conf.Keys.TryGetValue("2", out var v2) ? v2.Split("\\").Last() : "Non défini";
                button3.Text    = conf.Keys.TryGetValue("3", out var v3) ? v3.Split("\\").Last() : "Non défini";
                button4.Text    = conf.Keys.TryGetValue("4", out var v4) ? v4.Split("\\").Last() : "Non défini";
                button5.Text    = conf.Keys.TryGetValue("5", out var v5) ? v5.Split("\\").Last() : "Non défini";
                button6.Text    = conf.Keys.TryGetValue("6", out var v6) ? v6.Split("\\").Last() : "Non défini";
                button7.Text    = conf.Keys.TryGetValue("7", out var v7) ? v7.Split("\\").Last() : "Non défini";
                button8.Text    = conf.Keys.TryGetValue("8", out var v8) ? v8.Split("\\").Last() : "Non défini";
                button9.Text    = conf.Keys.TryGetValue("9", out var v9) ? v9.Split("\\").Last() : "Non défini";
                buttonPlus.Text = conf.Keys.TryGetValue("+", out var vPlus) ? vPlus.Split("\\").Last() : "Non défini";
                buttonMinus.Text= conf.Keys.TryGetValue("-", out var vMinus) ? vMinus.Split("\\").Last() : "Non défini";
                buttonStar.Text = conf.Keys.TryGetValue("*", out var vStar) ? vStar.Split("\\").Last() : "Non défini";
                buttonSlash.Text= conf.Keys.TryGetValue("/", out var vSlash) ? vSlash.Split("\\").Last() : "Non défini";
            });
        }

        public void Change_fStatusLabel2_Colors(Color BackgroundColor, Color ForegroundColor)
        {
            if (IsHandleCreated)
            {
                Invoke((MethodInvoker)delegate
                {
                    fStatusLabel2.BackColor = BackgroundColor;
                    fStatusLabel2.ForeColor = ForegroundColor;
                });
            }
        }
        public void Change_aStatusLabel2_Colors(Color BackgroundColor, Color ForegroundColor)
        {
            if (IsHandleCreated)
            {
                Invoke((MethodInvoker)delegate
                {
                    aStatusLabel2.BackColor = BackgroundColor;
                    aStatusLabel2.ForeColor = ForegroundColor;
                });
            }
        }
        public void Change_vStatusLabel2_Colors(Color BackgroundColor, Color ForegroundColor)
        {
            if (IsHandleCreated)
            {
                Invoke((MethodInvoker)delegate
                {
                    vStatusLabel2.BackColor = BackgroundColor;
                    vStatusLabel2.ForeColor = ForegroundColor;
                });
            }
        }

        public void Toggle_avStatusLabels()
        {
            if (IsHandleCreated)
            {
                Invoke((MethodInvoker)delegate
                {
                    aStatusLabel.Visible = !aStatusLabel.Visible;
                    aStatusLabel2.Visible = !aStatusLabel2.Visible;
                    vStatusLabel.Visible = !vStatusLabel.Visible;
                    vStatusLabel2.Visible = !vStatusLabel2.Visible;
                });
            }
        }

        private void buttonHome_Click(object sender, EventArgs e)
        {
            string input = Microsoft.VisualBasic.Interaction.InputBox("Entrez le tts :", "Que dire?", "Hello");
            Invoke((MethodInvoker)delegate
            {
                labelEnd2.Text = input;
            });
            Program.recognizedText = input;
            Program.SynthesizeSpeech();
        }

        private void MainForm_Load(object sender, EventArgs e)
        {
            Program.Load_X_Config(0);
            // Optionally you could re-check devices here if needed (keeps constructor minimal)
        }
    }

    // --- MMFinder copied / adapted from ShowMicVolume ---
    public static class MMFinder
    {
        public static MMDevice? GetMMDevice(string deviceName, DataFlow dataFlow = DataFlow.Render)
        {
            using var enumerator = new MMDeviceEnumerator();
            var endpoints = enumerator.EnumerateAudioEndPoints(dataFlow, DeviceState.Active);
            for (int i = 0; i < endpoints.Count; i++)
            {
                var device = endpoints[i];
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
