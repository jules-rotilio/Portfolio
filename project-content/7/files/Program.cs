using NAudio.Vorbis;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;
using NVorbis;
using System;
using System.Diagnostics;
using System.Globalization;
using System.Media;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.InteropServices;
using System.Speech.Recognition;
using System.Speech.Synthesis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;


namespace scp_sl_v2
{
    public partial class Program
    {
        private const int WH_KEYBOARD_LL = 13;
        private const int WH_MOUSE_LL = 14;
        private const int WM_KEYDOWN = 0x0100;
        private const int WM_KEYUP = 0x0101;
        private const int WM_MOUSEWHEEL = 0x020A;
        private const uint KEYEVENTF_KEYUP = 0x0002;

        private static LowLevelKeyboardProc _keyboardProc = KeyboardHookCallback;
        private static LowLevelMouseProc _mouseProc = MouseHookCallback;
        private static IntPtr _keyboardHookID = IntPtr.Zero;
        private static IntPtr _mouseHookID = IntPtr.Zero;

        private static bool vKeyPressed = false;
        private static bool aKeyPressed = false;
        private static int selectedKey = VK_A;
        private static bool toggleF = false;
        private const int VK_CONTROL = 0x11;
        private const int VK_ENTER = 0x0D;

        private const int VK_F = 0x46;
        private const int VK_A = 0x41;
        private const int VK_V = 0x56;

        private const int VK_NUMPAD0 = 0x60;
        private const int VK_NUMPAD1 = 0x61;
        private const int VK_NUMPAD2 = 0x62;
        private const int VK_NUMPAD3 = 0x63;
        private const int VK_NUMPAD4 = 0x64;
        private const int VK_NUMPAD5 = 0x65;
        private const int VK_NUMPAD6 = 0x66;
        private const int VK_NUMPAD7 = 0x67;
        private const int VK_NUMPAD8 = 0x68;
        private const int VK_NUMPAD9 = 0x69;

        private const int VK_MULTIPLY = 0x6A;
        private const int VK_ADD = 0x6B;
        private const int VK_SUBTRACT = 0x6D;
        private const int VK_DECIMAL = 0x6E;
        private const int VK_DIVIDE = 0x6F;

        private const int VK_PRIOR = 0x21;
        private const int VK_NEXT = 0x22;

        private const int VK_END = 0x23;
        private const int VK_HOME = 0x24;

        private const int VK_LEFT = 0x25;
        private const int VK_RIGHT = 0x27;

        private const int MOUSEEVENTF_MOVE = 0x0001;

        private static bool GoLeft = false;
        private static bool GoRight = false;

        private static bool IsScpSlFocused = false;
        private static bool PreviousScpSlFocused = false;

        private static WaveOutEvent audioPlayer = new()
        {
            DeviceNumber = GetAudioDevice()
        };
        private static AudioFileReader? audioReader;
        private static VorbisWaveReader? vorbisReader;
        private static float Volume
        {
            get => audioPlayer.Volume;
            set => audioPlayer.Volume = value;
        }

        private static int _audioDeviceNumber = 1;

        private static bool isRecording = false;
        private static MemoryStream recordedAudio = new MemoryStream();
        private static WaveInEvent waveIn;
        public static string recognizedText = "";
        private static string ttsWavFile = "tts_output.wav";

        private static MainForm mainForm;
        public static ConfigsList configsList;
        private static Config? currentConfig;
        private static int pageNumber = 1;


        public static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            Load_Configs();
            mainForm = new();


            GetInputDevice();
            _keyboardHookID = SetKeyboardHook(_keyboardProc);
            _mouseHookID = SetMouseHook(_mouseProc);

            new Thread(() =>
            {
                while (true)
                {
                    int DeviceNumber = GetAudioDevice();
                    audioPlayer.DeviceNumber = DeviceNumber;
                    //Debug.WriteLine(DeviceNumber);
                    Thread.Sleep(1000);
                }
            }).Start();

            new Thread(() =>
            {
                while (true)
                {
                    PreviousScpSlFocused = IsScpSlFocused; // Sauvegarde l'état précédent
                    ScpSlFocused(); // Met à jour IsScpSlFocused

                    // Exécute le bloc seulement si on vient de perdre le focus
                    if (PreviousScpSlFocused && !IsScpSlFocused)
                    {
                        GoLeft = false;
                        GoRight = false;
                        ReleaseKey(VK_A);
                        ReleaseKey(VK_V);
                        ReleaseKey(VK_F);
                        vKeyPressed = false;
                        aKeyPressed = false;
                        toggleF = false;
                        StopAudio();
                        ResetScrollLock();
                        mainForm.Change_aStatusLabel2_Colors(Color.Transparent, SystemColors.ControlText);
                        mainForm.Change_vStatusLabel2_Colors(Color.Transparent, SystemColors.ControlText);
                        mainForm.Change_fStatusLabel2_Colors(Color.Transparent, SystemColors.ControlText);
                    }
                    Thread.Sleep(1000);
                }
            }).Start();

            new Thread(LeftThread).Start();
            new Thread(RightThread).Start();

            
            Application.Run(mainForm);

            UnhookWindowsHookEx(_keyboardHookID);
            UnhookWindowsHookEx(_mouseHookID);
        }

        private static void Load_Configs()
        {
            string configPath = "AudioConfig.json";
            if (File.Exists(configPath))
            {
                string json = File.ReadAllText(configPath);
                var dict = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, string>>>(json);
                configsList = new ConfigsList();
                if (dict != null)
                {
                    foreach (var entry in dict)
                    {
                        configsList.Configs[entry.Key] = new Config { Keys = entry.Value };
                    }
                }
            }
            else
            {
                configsList = new ConfigsList
                {
                    Configs = { { "0", new Config() } }
                };
                string defaultJson = JsonSerializer.Serialize(configsList, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(configPath, defaultJson);
            }
        }

        private static void Save_Configs()
        {
            throw new NotImplementedException();
        }

        public static void Load_X_Config(int configNumber)
        {
            if (configsList.Configs.Count > configNumber && configNumber >= 0)
            {
                currentConfig = configsList.Configs[configNumber.ToString()];
            }
            else
            {
                currentConfig = new Config();
            }
            mainForm.UpdateButtons(currentConfig);
        }


        private static void ResetScrollLock()
        {
            // Get state of Scroll Lock : true if light is on, false if light is off
            bool scrollLockState = Control.IsKeyLocked(Keys.Scroll);
            // If Scroll Lock is on, turn it off
            if (scrollLockState)
            {
                // Simulate a key press to toggle Scroll Lock off
                PressKey((int)Keys.Scroll);
                Thread.Sleep(50);
                ReleaseKey((int)Keys.Scroll);
            }
        }

        private static IntPtr SetKeyboardHook(LowLevelKeyboardProc proc)
        {
            using (Process curProcess = Process.GetCurrentProcess())
            using (ProcessModule curModule = curProcess.MainModule)
            {
                return SetWindowsHookEx(WH_KEYBOARD_LL, proc, GetModuleHandle(curModule.ModuleName), 0);
            }
        }

        private static IntPtr SetMouseHook(LowLevelMouseProc proc)
        {
            using (Process curProcess = Process.GetCurrentProcess())
            using (ProcessModule curModule = curProcess.MainModule)
            {
                return SetWindowsHookEx(WH_MOUSE_LL, proc, GetModuleHandle(curModule.ModuleName), 0);
            }
        }

        private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);
        private delegate IntPtr LowLevelMouseProc(int nCode, IntPtr wParam, IntPtr lParam);

        private static IntPtr KeyboardHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode >= 0 && (wParam == (IntPtr)WM_KEYDOWN || wParam == (IntPtr)WM_KEYUP) && IsScpSlFocused)
            {
                int vkCode = Marshal.ReadInt32(lParam);
                if (wParam == (IntPtr)WM_KEYDOWN)
                {
                    OnKeyPress(vkCode);
                }
                else if (wParam == (IntPtr)WM_KEYUP)
                {
                    OnKeyRelease(vkCode);
                }
            }
            return CallNextHookEx(_keyboardHookID, nCode, wParam, lParam);
        }

        private static IntPtr MouseHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode >= 0 && wParam == (IntPtr)WM_MOUSEWHEEL && IsScpSlFocused)
            {
                MSLLHOOKSTRUCT hookStruct = (MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(MSLLHOOKSTRUCT));
                int delta = (short)((hookStruct.mouseData >> 16) & 0xffff);
                OnMouseWheel(delta);
            }
            return CallNextHookEx(_mouseHookID, nCode, wParam, lParam);
        }

        private static void OnKeyPress(int vkCode)
        {
            if (vkCode == VK_NUMPAD0)
            {
                toggleF = !toggleF;
                //PrintStatus();
                if (toggleF)
                {
                    new Thread(PressF).Start();
                    new Thread(FBlink).Start();
                }
            }
            else if (vkCode == VK_NEXT || vkCode == VK_PRIOR)
            {
                if (vkCode == VK_NEXT)
                {
                    pageNumber++;
                    mainForm.UpdatePageLabel(pageNumber.ToString());
                }
                else
                {
                    pageNumber--;
                    if (pageNumber < 0) { pageNumber = 0; }
                    else mainForm.UpdatePageLabel(pageNumber.ToString());
                }
                Load_X_Config(pageNumber);
            }
            else if ((vkCode >= VK_NUMPAD1 && vkCode <= VK_NUMPAD9) || (vkCode >= VK_MULTIPLY && vkCode <= VK_DIVIDE))
            {
                //PlaySound(vkCode);
            }
            else if (vkCode == (int)Keys.Scroll)
            {
                switch (selectedKey)
                {
                    case VK_A:
                        ToggleAKey();
                        break;
                    case VK_V:
                        ToggleVKey();
                        break;
                }
            }
            else if (vkCode == (int)Keys.Pause)
            {
                mainForm.Close();
                Environment.Exit(0);

            }
            else if (vkCode == (int)Keys.Insert)
            {
                selectedKey = selectedKey == VK_A ? VK_V : VK_A;
                ReleaseKey(VK_A);
                ReleaseKey(VK_V);
                ResetScrollLock();
                mainForm.Toggle_avStatusLabels();
            }
            else if (vkCode == (int)Keys.Up)
            {
                if (Math.Round(Volume, 1) <= 0.9)
                {
                    Volume = (float)Math.Round(Volume + 0.1f, 1);
                }
            }
            else if (vkCode == (int)Keys.Down)
            {
                if (Math.Round(Volume, 1) >= 0.1)
                {
                    Volume = (float)Math.Round(Volume - 0.1f, 1);
                }
            }
            else if (vkCode == VK_LEFT)
            {
                GoLeft = !GoLeft;
                GoRight = false;
            }
            else if (vkCode == VK_RIGHT)
            {
                GoRight = !GoRight;
                GoLeft = false;
            }
            else if (vkCode == VK_HOME && !isRecording)
            {
                //StartRecording();
                // turn into thread
                new Thread(() =>
                {
                    StartRecording();
                }).Start();
                Console.WriteLine("Recording thread started.");

            }
            else if (vkCode == VK_END)
            {
                PlaySynthesis();
            }

        }

        private static void OnKeyRelease(int vkCode)
        {
            // Handle key release if needed
            if (vkCode == VK_HOME && isRecording)
            {
                StopRecording();
            }
        }

        private static void OnMouseWheel(int delta)
        {
            if (delta > 0)
            {
                // Molette vers le haut
                // press the &1 key
                PressKey(0x31);
                ReleaseKey(0x31);
            }
            else if (delta < 0)
            {
                // Molette vers le bas
                // press the é2~ key
                PressKey(0x32);
                ReleaseKey(0x32);
            }
        }

        private static void ToggleAKey()
        {
            Color BackgroundColor;
            Color ForegroundColor;
            if (aKeyPressed)
            {
                ReleaseKey(selectedKey);
                BackgroundColor = Color.Transparent;
                ForegroundColor = SystemColors.ControlText;
                mainForm.Change_aStatusLabel2_Colors(BackgroundColor, ForegroundColor);
            }
            else
            {
                PressKey(selectedKey);
                BackgroundColor = Color.Lime;
                ForegroundColor = Color.Black;
                mainForm.Change_aStatusLabel2_Colors(BackgroundColor, ForegroundColor);
            }
            aKeyPressed = !aKeyPressed;
        }
        private static void ToggleVKey()
        {
            Color BackgroundColor;
            Color ForegroundColor;
            if (vKeyPressed)
            {
                ReleaseKey(selectedKey);
                BackgroundColor = Color.Transparent;
                ForegroundColor = SystemColors.ControlText;
                mainForm.Change_vStatusLabel2_Colors(ForegroundColor, BackgroundColor);
            }
            else
            {
                PressKey(selectedKey);
                BackgroundColor = Color.Lime;
                ForegroundColor = Color.Black;
                mainForm.Change_vStatusLabel2_Colors(BackgroundColor, ForegroundColor);
            }
            vKeyPressed = !vKeyPressed;
        }

        private static void PressF()
        {
            while (toggleF)
            {
                PressKey(VK_F);
                Thread.Sleep(50);
                ReleaseKey(VK_F);
                Thread.Sleep(50);
            }
        }

        private static void FBlink()
        {
            while (toggleF)
            {
                Color BackgroundColor = Color.Blue;
                Color ForegroundColor = Color.White;
                mainForm.Change_fStatusLabel2_Colors(BackgroundColor, ForegroundColor);
                Thread.Sleep(1000);
                BackgroundColor = Color.Transparent;
                ForegroundColor = SystemColors.ControlText;
                mainForm.Change_fStatusLabel2_Colors(BackgroundColor, ForegroundColor);
                Thread.Sleep(1000);

            }
        }

        private static void LeftThread()
        {
            while (true)
            {
                if (GoLeft)
                {
                    MoveMouse(-15, 0);
                    Thread.Sleep(20);
                }
                else
                {
                    Thread.Sleep(200);
                }
            }
        }

        private static void RightThread()
        {
            while (true)
            {
                if (GoRight)
                {
                    MoveMouse(15, 0);
                    Thread.Sleep(20);
                }
                else
                {
                    Thread.Sleep(200);
                }

            }
        }


        

        private static void PlaySound(int vkCode)
        {
            if (currentConfig == null) return;
            if (currentConfig.Keys == null) return;
            string key = vkCode switch
            {
                VK_NUMPAD1 => "1",
                VK_NUMPAD2 => "2",
                VK_NUMPAD3 => "3",
                VK_NUMPAD4 => "4",
                VK_NUMPAD5 => "5",
                VK_NUMPAD6 => "6",
                VK_NUMPAD7 => "7",
                VK_NUMPAD8 => "8",
                VK_NUMPAD9 => "9",
                VK_ADD => "+",
                VK_SUBTRACT => "-",
                VK_DIVIDE => "/",
                VK_MULTIPLY => "*",
                _ => ""
            };

            if (key == "") return;

            if (vkCode == VK_DECIMAL)
            {
                StopAudio();
            }
            else if (currentConfig.Keys.TryGetValue(key, out string soundPath) && soundPath != "")
            {
                PlayAudio(soundPath);
            }
        }
        /*
        {
            string soundPath = vkCode switch
            {
                VK_NUMPAD1 => GetRandomSound(new string[]
                {
            "C:\\Users\\jules\\Music\\HL - scientists\\helloladies.wav",
            "C:\\Users\\jules\\Music\\HL - scientists\\goodmorninggordon.wav",
            "C:\\Users\\jules\\Music\\HL - scientists\\gooodmorninggordon.wav",
            "C:\\Users\\jules\\Music\\HL - scientists\\greetings.wav",
            "C:\\Users\\jules\\Music\\HL - scientists\\greetings2.wav"
                }),
                VK_NUMPAD2 => GetRandomSound(new string[]
                {
            "C:\\Users\\jules\\Music\\HL - scientists\\yes.wav",
            "C:\\Users\\jules\\Music\\HL - scientists\\yes2.wav"
                }),
                VK_NUMPAD3 => GetRandomSound(new string[]
                {
            "C:\\Users\\jules\\Music\\HL - scientists\\noo.wav",
            "C:\\Users\\jules\\Music\\HL - scientists\\no!.wav"
                }),
                VK_NUMPAD4 => "C:\\Users\\jules\\Music\\HL - scientists\\madness.wav",
                VK_NUMPAD5 => "C:\\Users\\jules\\Music\\HL - scientists\\ohmygodweredoomed.wav",
                VK_NUMPAD6 => "C:\\Users\\jules\\Music\\HL - scientists\\yesletsgo.wav",
                VK_NUMPAD7 => "C:\\Users\\jules\\Music\\HL - scientists\\whatyoudoing.wav",
                VK_NUMPAD8 => "C:\\Users\\jules\\Music\\HL - scientists\\noplease.wav",
                VK_NUMPAD9 => "C:\\Users\\jules\\Music\\HL - scientists\\dontshootimwiththescienceteam.wav",
                VK_ADD => "C:\\Users\\jules\\Music\\doot.mp3",
                VK_SUBTRACT => GetRandomSound(new string[]
                {
                "C:\\Users\\jules\\Music\\Minecraft\\Cave Sounds\\Cave00001(1).mp3",
                "C:\\Users\\jules\\Music\\Minecraft\\Cave Sounds\\Cave00010(2).mp3",
                "C:\\Users\\jules\\Music\\Minecraft\\Cave Sounds\\Cave00101(5).mp3",
                "C:\\Users\\jules\\Music\\Minecraft\\Cave Sounds\\Cave01010(10).mp3",
                "C:\\Users\\jules\\Music\\Minecraft\\Cave Sounds\\Cave10011(19).mp3"
                }),
                VK_DIVIDE => GetRandomSound(
                    [
                    "C:\\Users\\jules\\Music\\HL - scientists\\importantwork0.wav",
                "C:\\Users\\jules\\Music\\HL - scientists\\importantwork1.wav",
                "C:\\Users\\jules\\Music\\HL - scientists\\importantwork2.wav",
                "C:\\Users\\jules\\Music\\HL - scientists\\importantwork3.wav",
                "C:\\Users\\jules\\Music\\HL - scientists\\importantwork4.wav",
                "C:\\Users\\jules\\Music\\HL - scientists\\importantwork5.wav",
                "C:\\Users\\jules\\Music\\HL - scientists\\importantwork6.wav",

            ]),
                VK_MULTIPLY => "C:\\Users\\jules\\Music\\ka-boom.mp3",
                VK_NEXT => "C:\\Users\\jules\\Music\\Allahu_Akbar.mp3",
                VK_PRIOR => "C:\\Users\\jules\\Music\\LowTierGod.mp3",
                VK_ENTER => GetRandomSound(new string[]
                {
                "C:\\Users\\jules\\Music\\SpyAmongUs.mp3",
                "C:\\Users\\jules\\Music\\SpyGentlemen.ogg",
                "C:\\Users\\jules\\Music\\SoldierSpy.ogg"
                }),
                _ => ""
            };
            if (vkCode == VK_DECIMAL)
            {
                StopAudio();
            }
            else if (soundPath != "")
            {
                PlayAudio(soundPath);
            }
        }
        */
        private static void PlayAudio(string path, bool amplifyTheVolume = false)
        {
            StopAudio();
            if (path.EndsWith(".wav") || path.EndsWith(".mp3"))
            {
                audioReader = new AudioFileReader(path);
                if (amplifyTheVolume)
                {
                    var sampleProvider = new VolumeSampleProvider(audioReader.ToSampleProvider())
                    {
                        Volume = 2.0f
                    };
                    audioPlayer.Init(sampleProvider);
                }
                else
                {
                    audioPlayer.Init(audioReader);
                }
            }
            else if (path.EndsWith(".ogg"))
            {
                vorbisReader = new VorbisWaveReader(path);
                audioPlayer.Init(vorbisReader);
            }
            audioPlayer.Play();
        }

        private static void StopAudio()
        {
            audioPlayer.Stop();
            audioReader?.Dispose();
            vorbisReader?.Dispose();
        }

        private static int GetAudioDevice()
        {
            var devices = WaveOut.DeviceCount;
            for (int i = 0; i < devices; i++)
            {
                var capabilities = WaveOut.GetCapabilities(i);
                //Debug.WriteLine(capabilities.ProductName);
                if (capabilities.ProductName.StartsWith("Hi-Fi"))
                {
                    return i;
                }
            }
            return -1; // Return -1 if no non-default device is found
        }


        public static void GetInputDevice()
        {
            for (int i = 0; i < WaveIn.DeviceCount; i++)
            {
                var info = WaveIn.GetCapabilities(i);
                if (info.ProductName.StartsWith("Microphone (WO Mic Device)"))
                {
                    _audioDeviceNumber = i;
                }
            }
        }
        private static void StartRecording()
        {
            isRecording = true;
            recordedAudio = new MemoryStream();
            waveIn = new WaveInEvent();
            waveIn.DeviceNumber = _audioDeviceNumber; // Choix du micro
            waveIn.WaveFormat = new WaveFormat(16000, 1);
            waveIn.DataAvailable += (s, a) => recordedAudio.Write(a.Buffer, 0, a.BytesRecorded);
            waveIn.StartRecording();
            Console.WriteLine($"Recording...");
        }

        private static void StopRecording()
        {
            isRecording = false;
            waveIn.StopRecording();
            waveIn.Dispose();
            Console.WriteLine("Recording stopped. Recognizing...");
            RecognizeSpeech().GetAwaiter();
        }

        public static async Task<string> TranscribeWithWhisperAsync(string wavFilePath)
        {
            using var client = new HttpClient();
            using var form = new MultipartFormDataContent();
            using var fs = File.OpenRead(wavFilePath);
            form.Add(new StreamContent(fs)
            {
                Headers = { ContentType = new MediaTypeHeaderValue("audio/wav") }
            }, "file", Path.GetFileName(wavFilePath));

            Console.WriteLine("Envoi du fichier audio pour transcription...");
            var response = await client.PostAsync("http://127.0.0.1:8000/transcribe/", form);
            Console.WriteLine("Réponse du serveur : " + response.StatusCode);
            response.EnsureSuccessStatusCode();
            Console.WriteLine("Réponse reçue, traitement du JSON...");
            var json = await response.Content.ReadAsStringAsync();
            Console.WriteLine("JSON reçu : " + json);
            // Extraire le texte du JSON (simple, sans dépendance JSON)
            var idx = json.IndexOf(":");
            var txt = json.Substring(idx + 2, json.Length - idx - 4);
            return txt;
        }

        private async static Task RecognizeSpeech()
        {
            recordedAudio.Position = 0;
            if (recordedAudio.Length == 0)
            {
                Console.WriteLine("Aucune donnée audio enregistrée.");
                return;
            }

            try
            {
                // Convertit le flux audio enregistré en un tableau de bytes .wav
                byte[] wavData;
                var waveFormat = new WaveFormat(16000, 1);
                using (var tempStream = new MemoryStream())
                {
                    using (var writer = new WaveFileWriter(tempStream, waveFormat))
                    {
                        recordedAudio.Position = 0;
                        recordedAudio.CopyTo(writer);
                    }
                    wavData = tempStream.ToArray();
                }

                // --- Utilisation de Whisper via REST ---
                string tempWavPath = Path.GetTempFileName() + ".wav";
                File.WriteAllBytes(tempWavPath, wavData);

                try
                {
                    // Dans RecognizeSpeech, rendez la méthode async et utilisez await :
                    recognizedText = await TranscribeWithWhisperAsync(tempWavPath);
                    Console.WriteLine("Reconnu (Whisper) : " + recognizedText);
                }
                finally
                {
                    if (File.Exists(tempWavPath))
                        File.Delete(tempWavPath);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Erreur de reconnaissance vocale : " + ex.Message);
                Console.WriteLine(ex.StackTrace);
                Console.WriteLine(ex.GetType().Name);
            }

            SynthesizeSpeech();

            return;
        }

        public static void SynthesizeSpeech()
        {
            if (string.IsNullOrWhiteSpace(recognizedText)) return;
            StopAudio();
            if (File.Exists(ttsWavFile))
            {
                File.Delete(ttsWavFile);
            }
            using (var synth = new SpeechSynthesizer())
            {
                synth.SelectVoiceByHints(VoiceGender.Male, VoiceAge.Adult, 0, new CultureInfo("en-US"));
                synth.SetOutputToWaveFile(ttsWavFile);
                synth.Speak(recognizedText);
            }
        }

        private static void PlaySynthesis()
        {
            if (!File.Exists(ttsWavFile)) return;
            PlayAudio(ttsWavFile, true);
        }


        private static void PressKey(int keyCode)
        {
            keybd_event((byte)keyCode, 0, 0, 0);
        }

        private static void ReleaseKey(int keyCode)
        {
            keybd_event((byte)keyCode, 0, KEYEVENTF_KEYUP, 0);
        }

        private static void MoveMouse(int dx, int dy)
        {
            mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0);
        }


        private static void ScpSlFocused()
        {

            /*IsScpSlFocused = true; // Par défaut, on suppose que le jeu est en focus
            return;*/
            IntPtr foregroundWindow = GetForegroundWindow();
            if (foregroundWindow == IntPtr.Zero)
                IsScpSlFocused = false;

            GetWindowThreadProcessId(foregroundWindow, out uint processId);
            try
            {
                Process proc = Process.GetProcessById((int)processId);
                // Vérifie le nom du processus sans extension
                //IsScpSlFocused = proc.ProcessName.Equals("SCPSL", StringComparison.OrdinalIgnoreCase);
                IsScpSlFocused = proc.ProcessName.Equals("notepad", StringComparison.OrdinalIgnoreCase);
                // Ou avec extension si besoin :
                // return proc.MainModule.ModuleName.Equals("SCPSL.exe", StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                IsScpSlFocused = false;
            }
        }

        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelMouseProc lpfn, IntPtr hMod, uint dwThreadId);

        [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);

        [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool UnhookWindowsHookEx(IntPtr hhk);

        [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

        [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern IntPtr GetModuleHandle(string lpModuleName);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

        [DllImport("user32.dll")]
        private static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, int dwExtraInfo);

        [StructLayout(LayoutKind.Sequential)]
        private struct MSLLHOOKSTRUCT
        {
            public POINT pt;
            public uint mouseData;
            public uint flags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT
        {
            public int X;
            public int Y;
        }
    }

}