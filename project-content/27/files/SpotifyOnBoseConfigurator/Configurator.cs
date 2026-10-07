using Microsoft.Win32.TaskScheduler;

namespace SpotifyOnBoseConfigurator
{
    public partial class Configurator : Form
    {
        private string selectedTaskId = string.Empty;
        private string selectedTaskName = string.Empty;
        private bool newMode = false;
        private bool editMode = false;
        private bool changingTime = false;

        private static readonly Dictionary<string, string> DaysOfWeekInFrench = new()
        {
            { "Monday", "Lundi" },
            { "Tuesday", "Mardi" },
            { "Wednesday", "Mercredi" },
            { "Thursday", "Jeudi" },
            { "Friday", "Vendredi" },
            { "Saturday", "Samedi" },
            { "Sunday", "Dimanche" }
        };
        public Configurator()
        {
            InitializeComponent();
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            Load_Scheduled_Tasks();

        }

        private void Edit(object sender, EventArgs e)
        {

            if (newMode || changingTime) return;
            editMode = true;
            cancelButton.Visible = true;
            apply.Visible = true;

            var groupBox = splitContainer1.Panel1.Controls
            .OfType<TaskGroupBox>()
            .FirstOrDefault(g => g.task.Name == selectedTaskName);

            groupBox.BackColor = Color.Yellow;
            groupBox.ForeColor = Color.Black;

        }

        private void Select_Alarm(object sender, EventArgs e)
        {
            TaskGroupBox? groupBox = null;

            if (newMode) return;

            if (sender is TaskLabel label)
            {
                groupBox = label.Parent as TaskGroupBox;
                if (groupBox != null)
                {
                    Select_Alarm(groupBox, null);
                }
            }
            if (sender is TaskGroupBox)
            {
                groupBox = sender as TaskGroupBox;
                if (selectedTaskName == string.Empty)
                {
                    Load_Scheduled_Task(groupBox);
                }
                else
                {
                    var previousGroupBox = splitContainer1.Panel1.Controls
                        .OfType<TaskGroupBox>()
                        .FirstOrDefault(g => g.task.Name == selectedTaskName);
                    if (previousGroupBox != null)
                    {
                        if (previousGroupBox == groupBox)
                        {
                            Unload_Scheduled_Task(groupBox);
                            splitContainer1.Panel2Collapsed = true;
                        }
                        else
                        {
                            Unload_Scheduled_Task(previousGroupBox);
                            Load_Scheduled_Task(groupBox);
                        }
                    }
                    else
                    {
                        Load_Scheduled_Task(groupBox);
                    }
                }
            }
        }

        private void Load_Scheduled_Task(TaskGroupBox groupBox)
        {
            splitContainer1.Panel2Collapsed = false;
            selectedTaskName = groupBox.task.Name;
            selectedTaskId = selectedTaskName.Split("-{")[1].Replace("}", "");
            groupBox.BackColor = Color.SteelBlue;
            groupBox.ForeColor = Color.White;

            var task = groupBox.task;

            var time = task.Definition.Triggers
                        .OfType<Microsoft.Win32.TaskScheduler.WeeklyTrigger>()
                        .Select(trigger => trigger.StartBoundary.ToString("HH:mm"))
                        .FirstOrDefault();
            var daysOfWeek = task.Definition.Triggers
                        .OfType<Microsoft.Win32.TaskScheduler.WeeklyTrigger>()
                        .SelectMany(trigger => trigger.DaysOfWeek.ToString().Split(','))
                        .Select(day => day.Trim())
                        .Distinct();

            DeleteAlarmButton.Visible = true;

            mondayCheckBox.Checked = daysOfWeek.Contains("Monday");
            tuesdayCheckBox.Checked = daysOfWeek.Contains("Tuesday");
            wednesdayCheckBox.Checked = daysOfWeek.Contains("Wednesday");
            thursdayCheckBox.Checked = daysOfWeek.Contains("Thursday");
            fridayCheckBox.Checked = daysOfWeek.Contains("Friday");
            saturdayCheckBox.Checked = daysOfWeek.Contains("Saturday");
            sundayCheckBox.Checked = daysOfWeek.Contains("Sunday");

            changingTime = true;
            heureDateTimePicker.Value = DateTime.Today.AddHours(int.Parse(time.Split(':')[0])).AddMinutes(int.Parse(time.Split(':')[1]));
            changingTime = false;


            TaskConfiguration taskConfiguration = new(selectedTaskId);
            UrlTextBox.Text = taskConfiguration.URL;
            if (taskConfiguration.ProgressiveVolume)
            {
                progressiveVolumeCheckBox.Checked = true;
                minVolumeTextBox.Text = taskConfiguration.VolumeMin.ToString();
                maxVolumeTextBox.Text = taskConfiguration.VolumeMax.ToString();
                volumeIncreasePauseTextBox.Text = taskConfiguration.VolumeIncreaseDelay.ToString();
                volumeIncreaseTextBox.Text = taskConfiguration.VolumeIncrease.ToString();
            }
            else
            {
                flatVolumeTextBox.Text = taskConfiguration.VolumeFlat.ToString();
            }
            shuffleCheckBox.Checked = taskConfiguration.Shuffle;
            if (taskConfiguration.Play1Song)
            {
                play1SongCheckBox.Checked = true;
            }
            else if (taskConfiguration.PlayXSeconds)
            {
                playXSecondsCheckBox.Checked = true;
                XSongsOrSecondsTextBox.Text = taskConfiguration.X.ToString();
            }
            else if (taskConfiguration.PlayXSongs)
            {
                playXSongsCheckBox.Checked = true;
                XSongsOrSecondsTextBox.Text = taskConfiguration.X.ToString();
            }
            SpeakerNameTextBox.Text = taskConfiguration.SpeakerName;

        }

        private void Unload_Scheduled_Task(TaskGroupBox groupBox, bool justTheColor = false)
        {
            groupBox.BackColor = Color.AliceBlue;
            groupBox.ForeColor = Color.Black;
            selectedTaskId = string.Empty;
            selectedTaskName = string.Empty;

            if (justTheColor)
            {
                return;
            }

            mondayCheckBox.Checked = false;
            tuesdayCheckBox.Checked = false;
            wednesdayCheckBox.Checked = false;
            thursdayCheckBox.Checked = false;
            fridayCheckBox.Checked = false;
            saturdayCheckBox.Checked = false;
            sundayCheckBox.Checked = false;

            changingTime = true;
            heureDateTimePicker.Value = DateTime.Today.AddHours(6).AddMinutes(45);
            changingTime = false;

            UrlTextBox.Text = string.Empty;

            flatVolumeTextBox.Text = "35";

            progressiveVolumeCheckBox.Checked = false;
            minVolumeTextBox.Text = "10";
            maxVolumeTextBox.Text = "45";

            shuffleCheckBox.Checked = false;

            play1SongCheckBox.Checked = false;
            playXSecondsCheckBox.Checked = false;
            playXSongsCheckBox.Checked = false;
            XSongsOrSecondsTextBox.Text = "";

            volumeIncreasePauseTextBox.Text = "";
            volumeIncreaseTextBox.Text = "";

            DeleteAlarmButton.Visible = false;
        }

        private void Load_Scheduled_Tasks()
        {
            // Remove any existing TaskGroupBox controls from the panel Panel1
            foreach (var control in splitContainer1.Panel1.Controls.OfType<TaskGroupBox>().ToList())
            {
                splitContainer1.Panel1.Controls.Remove(control);
                control.Dispose();
            }

            using (var taskService = new Microsoft.Win32.TaskScheduler.TaskService())
            {
                var tasks = taskService.AllTasks
                    .Where(task => task.Name.StartsWith("SpotifyOnBose-"));

                int yOffset = 3;

                foreach (var task in tasks)
                {
                    var groupBox = new TaskGroupBox(task);
                    groupBox.Text = task.Definition.RegistrationInfo.Description;
                    groupBox.Location = new Point(3, yOffset);
                    groupBox.Size = new Size(422, 70);
                    groupBox.Anchor = AnchorStyles.Top | AnchorStyles.Left;
                    groupBox.BackColor = Color.AliceBlue;
                    groupBox.Click += Select_Alarm; // Ajout de l'événement Click
                    groupBox.Paint += (s, e) =>
                    {
                        // Dessiner une bordure autour du GroupBox
                        ControlPaint.DrawBorder(e.Graphics, groupBox.ClientRectangle,
                            Color.Black, ButtonBorderStyle.Solid);
                    };

                    var label1 = new TaskLabel();
                    label1.Text = "Jours de la semaine : ";
                    label1.Location = new Point(10, 20);
                    label1.AutoSize = true;
                    label1.Click += Select_Alarm; // Ajout de l'événement Click
                    groupBox.Controls.Add(label1);

                    // Récupérer les jours de la semaine
                    var daysOfWeek = task.Definition.Triggers
                        .OfType<Microsoft.Win32.TaskScheduler.WeeklyTrigger>()
                        .SelectMany(trigger => trigger.DaysOfWeek.ToString().Split(','))
                        .Select(day => day.Trim())
                        .Distinct();

                    // Convertir les jours en français et les ajouter au label
                    var daysInFrench = daysOfWeek
                        .Where(day => DaysOfWeekInFrench.ContainsKey(day))
                        .Select(day => DaysOfWeekInFrench[day]);

                    label1.Text += string.Join(", ", daysInFrench);

                    // Créer un label pour l'heure
                    var label2 = new TaskLabel();
                    label2.Text = "Heure : ";
                    label2.Location = new Point(10, 40);
                    label2.AutoSize = true;
                    label2.Click += Select_Alarm; // Ajout de l'événement Click
                    groupBox.Controls.Add(label2);

                    // Récupérer l'heure
                    var time = task.Definition.Triggers
                        .OfType<Microsoft.Win32.TaskScheduler.WeeklyTrigger>()
                        .Select(trigger => trigger.StartBoundary.ToString("HH:mm"))
                        .FirstOrDefault();
                    if (time != null)
                    {
                        label2.Text += time;
                    }

                    splitContainer1.Panel1.Controls.Add(groupBox);
                    yOffset += groupBox.Height + 5;
                }
            }
        }



        private void button2_Click(object sender, EventArgs e)
        {
            // Supprimer la tâche
            using (var taskService = new Microsoft.Win32.TaskScheduler.TaskService())
            {
                taskService.RootFolder.DeleteTask(selectedTaskName, false);
            }
            Load_Scheduled_Tasks();
        }

        private void cancelButton_Click(object sender, EventArgs e)
        {
            cancelButton.Visible = false;
            apply.Visible = false;
            if (newMode)
            {
                splitContainer1.Panel2Collapsed = true;
                newMode = false;
            }
            else
            {
                TaskGroupBox? groupBox = splitContainer1.Panel1.Controls
                    .OfType<TaskGroupBox>()
                    .FirstOrDefault(g => g.task.Name == selectedTaskName);
                Unload_Scheduled_Task(groupBox);
                editMode = false;
                Load_Scheduled_Task(groupBox);
            }
        }

        private void play1SongCheckBox_CheckedChanged(object sender, EventArgs e)
        {
            if (play1SongCheckBox.Checked)
            {
                playXSecondsCheckBox.Checked = false;
                playXSecondsCheckBox.Visible = false;
                playXSongsCheckBox.Checked = false;
                playXSongsCheckBox.Visible = false;
            }
            else
            {
                playXSecondsCheckBox.Visible = true;
                playXSongsCheckBox.Visible = true;
            }
        }
        private void progressiveVolumeCheckBox_CheckedChanged(object sender, EventArgs e)
        {
            if (progressiveVolumeCheckBox.Checked)
            {
                minVolumeTextBox.Visible = true;
                label4.Visible = true;
                maxVolumeTextBox.Visible = true;
                label5.Visible = true;
                volumeIncreasePauseTextBox.Visible = true;
                label7.Visible = true;
                volumeIncreaseTextBox.Visible = true;
                label8.Visible = true;

                flatVolumeTextBox.Visible = false;
                label6.Visible = false;
            }
            else
            {
                minVolumeTextBox.Visible = false;
                label4.Visible = false;
                maxVolumeTextBox.Visible = false;
                label5.Visible = false;
                volumeIncreasePauseTextBox.Visible = false;
                label7.Visible = false;
                volumeIncreaseTextBox.Visible = false;
                label8.Visible = false;

                flatVolumeTextBox.Visible = true;
                label6.Visible = true;
            }
        }
        private void playXSecondsCheckBox_CheckedChanged(object sender, EventArgs e)
        {
            if (playXSecondsCheckBox.Checked)
            {
                play1SongCheckBox.Checked = false;
                play1SongCheckBox.Visible = false;
                playXSongsCheckBox.Checked = false;
                playXSongsCheckBox.Visible = false;
                label2.Visible = true;
                XSongsOrSecondsTextBox.Visible = true;
            }
            else
            {
                playXSongsCheckBox.Visible = true;
                play1SongCheckBox.Visible = true;
                label2.Visible = false;
                XSongsOrSecondsTextBox.Visible = false;
            }
        }

        private void playXSongsCheckBox_CheckedChanged(object sender, EventArgs e)
        {
            if (playXSongsCheckBox.Checked)
            {
                play1SongCheckBox.Checked = false;
                play1SongCheckBox.Visible = false;
                playXSecondsCheckBox.Checked = false;
                playXSecondsCheckBox.Visible = false;
                label2.Visible = true;
                XSongsOrSecondsTextBox.Visible = true;
            }
            else
            {
                play1SongCheckBox.Visible = true;
                playXSecondsCheckBox.Visible = true;
                label2.Visible = false;
                XSongsOrSecondsTextBox.Visible = false;
            }
        }

        private void NewAlarmButton_Click(object sender, EventArgs e)
        {
            newMode = true;
            splitContainer1.Panel2Collapsed = false;
            cancelButton.Visible = true;
            apply.Visible = true;
        }

        private async void apply_Click(object sender, EventArgs e)
        {
            // Si en mode "new", générer un UUID4 pour selectedTaskId
            if (newMode)
            {
                selectedTaskId = Guid.NewGuid().ToString();
            }

            TaskConfiguration taskConfiguration = new TaskConfiguration
            {
                SpeakerName = SpeakerNameTextBox.Text,
                URL = UrlTextBox.Text,
                ProgressiveVolume = progressiveVolumeCheckBox.Checked,
                VolumeMin = progressiveVolumeCheckBox.Checked ? int.Parse(minVolumeTextBox.Text) : 0,
                VolumeMax = progressiveVolumeCheckBox.Checked ? int.Parse(maxVolumeTextBox.Text) : 0,
                VolumeFlat = progressiveVolumeCheckBox.Checked ? 0 : int.Parse(flatVolumeTextBox.Text),
                VolumeIncrease = progressiveVolumeCheckBox.Checked ? int.Parse(volumeIncreaseTextBox.Text) : 0,
                VolumeIncreaseDelay = progressiveVolumeCheckBox.Checked ? int.Parse(volumeIncreasePauseTextBox.Text) : 0,
                Play1Song = play1SongCheckBox.Checked,
                PlayXSeconds = playXSecondsCheckBox.Checked,
                PlayXSongs = playXSongsCheckBox.Checked,
                X = (playXSongsCheckBox.Checked || playXSecondsCheckBox.Checked) ? int.Parse(XSongsOrSecondsTextBox.Text) : 0,
                Shuffle = shuffleCheckBox.Checked
            };

            

            using (var taskService = new Microsoft.Win32.TaskScheduler.TaskService())
            {
                // Création ou récupération de la définition de la tâche
                var taskDefinition = newMode ? taskService.NewTask() : taskService.GetTask(selectedTaskName).Definition;

                // Configuration des jours de déclenchement
                var selectedDays = new List<DayOfWeek>();
                if (mondayCheckBox.Checked) selectedDays.Add(DayOfWeek.Monday);
                if (tuesdayCheckBox.Checked) selectedDays.Add(DayOfWeek.Tuesday);
                if (wednesdayCheckBox.Checked) selectedDays.Add(DayOfWeek.Wednesday);
                if (thursdayCheckBox.Checked) selectedDays.Add(DayOfWeek.Thursday);
                if (fridayCheckBox.Checked) selectedDays.Add(DayOfWeek.Friday);
                if (saturdayCheckBox.Checked) selectedDays.Add(DayOfWeek.Saturday);
                if (sundayCheckBox.Checked) selectedDays.Add(DayOfWeek.Sunday);

                // Configuration de la date et de l'heure de début
                var _startTime = heureDateTimePicker.Value;
                var _startDate = startDate.SelectionStart.Date;

                // Appel asynchrone à FetchSpotifyInfo
                var description = await SpotifyInfoFetcher.FetchSpotifyInfo(taskConfiguration.URL);
                if (string.IsNullOrEmpty(description))
                {
                    return;
                }

                taskConfiguration.Export(selectedTaskId);
                taskDefinition.RegistrationInfo.Description = description;

                taskDefinition.Triggers.Clear(); // Supprime les anciens déclencheurs
                var weeklyTrigger = new Microsoft.Win32.TaskScheduler.WeeklyTrigger
                {
                    StartBoundary = _startDate.Add(_startTime.TimeOfDay),
                    DaysOfWeek = selectedDays.Aggregate((DaysOfTheWeek)0, (current, day) => current | (DaysOfTheWeek)Enum.Parse(typeof(DaysOfTheWeek), day.ToString()))
                };
                taskDefinition.Triggers.Add(weeklyTrigger);

                // Définition de l'action à exécuter
                string appsettingsPath = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + "\\SpotifyOnBose\\appsettings-" + selectedTaskId + ".json";
                string spotifyOnBosePath = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + "\\SpotifyOnBose\\SpotifyOnBose.exe";
                taskDefinition.Actions.Clear(); // Supprime les anciennes actions
                taskDefinition.Actions.Add(new ExecAction(spotifyOnBosePath, appsettingsPath, null));

                // Enregistrement de la tâche (création ou mise à jour)
                taskService.RootFolder.RegisterTaskDefinition(
                    "SpotifyOnBose-{" + selectedTaskId + "}",
                    taskDefinition,
                    newMode ? TaskCreation.Create : TaskCreation.Update,
                    null,
                    null,
                    TaskLogonType.InteractiveToken,
                    null
                );
            }
            if (newMode)
            {
                splitContainer1.Panel2Collapsed = true;
                selectedTaskName = string.Empty;
                selectedTaskId = string.Empty;
            }
            if (editMode)
            {
                TaskGroupBox? groupBox = splitContainer1.Panel1.Controls
                    .OfType<TaskGroupBox>()
                    .FirstOrDefault(g => g.task.Name == selectedTaskName);
                Unload_Scheduled_Task(groupBox);
                splitContainer1.Panel2Collapsed = true;
            }
            // Réinitialisation des modes
            newMode = false;
            editMode = false;
            cancelButton.Visible = false;
            apply.Visible = false;

            Load_Scheduled_Tasks();
        }



    }
}
