using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace SpotifyOnBoseConfigurator
{
    internal class TaskConfiguration
    {
        private static readonly string settingsPath = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + "\\SpotifyOnBose\\appsettings-{0}.json";
        public TaskConfiguration(string taskID)
        {

            string json = System.IO.File.ReadAllText(string.Format(settingsPath, taskID));
            TaskConfiguration taskConfig = JsonConvert.DeserializeObject<TaskConfiguration>(json) ?? throw new Exception("Failed to deserialize TaskConfiguration from JSON file.");
            SpeakerName = taskConfig.SpeakerName;
            URL = taskConfig.URL;
            Shuffle = taskConfig.Shuffle;
            ProgressiveVolume = taskConfig.ProgressiveVolume;
            VolumeMin = taskConfig.VolumeMin;
            VolumeMax = taskConfig.VolumeMax;
            VolumeFlat = taskConfig.VolumeFlat;
            VolumeIncrease = taskConfig.VolumeIncrease;
            VolumeIncreaseDelay = taskConfig.VolumeIncreaseDelay;
            Play1Song = taskConfig.Play1Song;
            PlayXSeconds = taskConfig.PlayXSeconds;
            PlayXSongs = taskConfig.PlayXSongs;
            X = taskConfig.X;
        }

        public TaskConfiguration()
        {
            SpeakerName = string.Empty;
            URL = string.Empty;
            Shuffle = false;
            ProgressiveVolume = false;
            VolumeMin = 10;
            VolumeMax = 46;
            VolumeFlat = 0;
            VolumeIncrease = 0;
            VolumeIncreaseDelay = 0;
            Play1Song = false;
            PlayXSeconds = false;
            PlayXSongs = false;
            X = 0;
        }

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

        public void Export(string taskID)
        {
            string json = JsonConvert.SerializeObject(this, Formatting.Indented);
            System.IO.File.WriteAllText(string.Format(settingsPath, taskID), json);
        }

    }
}