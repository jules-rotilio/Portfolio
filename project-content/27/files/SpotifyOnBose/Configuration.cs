using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace SpotifyAlarmClockOnBose
{
    internal class Configuration
    {
        public static string settingsPath;

        private static Configuration? Instance { get; set; }
        public string SpeakerName;
        public string URL;
        public bool Shuffle;
        public bool ProgressiveVolume;
        public int VolumeMin;
        public int VolumeMax;
        public int VolumeFlat;
        public int VolumeIncrease;
        public int VolumeIncreaseDelay;
        public bool Play1Song;
        public bool PlayXSeconds;
        public bool PlayXSongs;
        public int X;



        private Configuration() { }

        public static Configuration Load()
        {
            string json = System.IO.File.ReadAllText(settingsPath);
            return JsonConvert.DeserializeObject<Configuration>(json) ?? throw new Exception("Configuration file is not valid.");
        }

        public static Configuration GetInstance()
        {
            Instance ??= Load();
            return Instance;
        }

    }
}
