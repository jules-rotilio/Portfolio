using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Xml;
using System.Windows.Forms;
using System.Diagnostics;

namespace SpotifyAlarmClockOnBose
{
    class Program
    {
        static void Main(string[] args)
        {
            Run(args[0]).GetAwaiter().GetResult();
        }

        static async Task Run(string appsettings_path)
        {
            Configuration.settingsPath = appsettings_path;

            BoseSpeaker bose;
            try
            {
                bose = await BoseDetector.GetBoseSpeaker();
            }
            catch (BoseNotFoundException e)
            {
                MessageBox.Show(e.Message);
                return;
            }
            catch (Exception e)
            {
                MessageBox.Show(e.StackTrace, "ERREUR!!!!");
                return;
            }

            Configuration config = Configuration.GetInstance();
            if (config.Shuffle)
            {
                await bose.ShuffleOn();
            }
            else
            {
                await bose.ShuffleOff();
            }

            // reset music
            await bose.SetVolume(0);
            await bose.Play("https://open.spotify.com/intl-fr/track/4bO6DljpuAeQh6HS20i0I5?si=21d4cc1bebe542f7");
            await Task.Delay(2000);
            await bose.TurnOff();
            await Task.Delay(2000);

            if (config.ProgressiveVolume)
            {
                Debug.WriteLine("Progressive volume on");
                await bose.SetVolume(config.VolumeMin);
                await bose.Play(config.URL);
                for (int i = config.VolumeMin; i <= config.VolumeMax; i += config.VolumeIncrease)
                {
                    await bose.SetVolume(i);
                    Debug.WriteLine("set volume " + i);
                    await Task.Delay(config.VolumeIncreaseDelay * 1000);
                }
            }
            else
            {
                await bose.SetVolume(config.VolumeFlat);
                await bose.Play(config.URL);
            }

            // set start time
            DateTime startTime = DateTime.Now;

            if (config.Play1Song)
            {
                while (await bose.GetProgress() < 97)
                {
                    await Task.Delay(500);
                }
                await bose.Pause();
            }
            else if (config.PlayXSeconds)
            {
                // get the current time
                DateTime currentTime = DateTime.Now;
                int delta = (int)(currentTime - startTime).TotalSeconds;
                await Task.Delay((config.X - delta) * 1000);
                await bose.Pause();
            }
            else if (config.PlayXSongs)
            {
                // get the current track
                var track = await bose.GetTrack();
                for (int i = 0; i < config.X - 1; i++)
                {
                    // wait for the track to change
                    while (await bose.GetTrack() == track)
                    {
                        await Task.Delay(500);
                    }
                    // wait for the next track to start
                    await Task.Delay(3000);
                    // get the next track
                    track = await bose.GetTrack();

                }
                while (await bose.GetProgress() < 97 && await bose.GetTrack() == track)
                {
                    await Task.Delay(500);
                }
                await bose.Pause();
            }

        }
    }
}