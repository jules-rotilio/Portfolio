using System.Windows.Forms;

namespace SpotifyOnBoseConfigurator
{
    partial class Configurator
    {
        /// <summary>
        ///  Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        ///  Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        ///  Required method for Designer support - do not modify
        ///  the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            apply = new Button();
            startDate = new MonthCalendar();
            daysOfTheWeek = new Label();
            mondayCheckBox = new CheckBox();
            tuesdayCheckBox = new CheckBox();
            wednesdayCheckBox = new CheckBox();
            thursdayCheckBox = new CheckBox();
            fridayCheckBox = new CheckBox();
            saturdayCheckBox = new CheckBox();
            sundayCheckBox = new CheckBox();
            time = new Label();
            heureDateTimePicker = new DateTimePicker();
            label1 = new Label();
            UrlTextBox = new TextBox();
            play1SongCheckBox = new CheckBox();
            playXSongsCheckBox = new CheckBox();
            playXSecondsCheckBox = new CheckBox();
            XSongsOrSecondsTextBox = new TextBox();
            label2 = new Label();
            label3 = new Label();
            label4 = new Label();
            label5 = new Label();
            SpeakerNameTextBox = new TextBox();
            shuffleCheckBox = new CheckBox();
            progressiveVolumeCheckBox = new CheckBox();
            minVolumeTextBox = new TextBox();
            maxVolumeTextBox = new TextBox();
            label6 = new Label();
            flatVolumeTextBox = new TextBox();
            label7 = new Label();
            volumeIncreasePauseTextBox = new TextBox();
            label8 = new Label();
            volumeIncreaseTextBox = new TextBox();
            startDateLabel = new Label();
            splitContainer1 = new SplitContainer();
            DeleteAlarmButton = new Button();
            NewAlarmButton = new Button();
            cancelButton = new Button();
            ((System.ComponentModel.ISupportInitialize)splitContainer1).BeginInit();
            splitContainer1.Panel1.SuspendLayout();
            splitContainer1.Panel2.SuspendLayout();
            splitContainer1.SuspendLayout();
            SuspendLayout();
            // 
            // apply
            // 
            apply.BackColor = Color.PaleGreen;
            apply.FlatAppearance.BorderColor = Color.Lime;
            apply.FlatStyle = FlatStyle.Flat;
            apply.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            apply.Location = new Point(660, 508);
            apply.Name = "apply";
            apply.Size = new Size(148, 47);
            apply.TabIndex = 1;
            apply.Text = "Valider";
            apply.UseVisualStyleBackColor = false;
            apply.Visible = false;
            apply.Click += apply_Click;
            // 
            // startDate
            // 
            startDate.Location = new Point(122, 9);
            startDate.Name = "startDate";
            startDate.TabIndex = 2;
            // 
            // daysOfTheWeek
            // 
            daysOfTheWeek.AutoSize = true;
            daysOfTheWeek.Location = new Point(11, 197);
            daysOfTheWeek.Name = "daysOfTheWeek";
            daysOfTheWeek.Size = new Size(104, 15);
            daysOfTheWeek.TabIndex = 4;
            daysOfTheWeek.Text = "Jour de la semaine";
            // 
            // mondayCheckBox
            // 
            mondayCheckBox.AutoSize = true;
            mondayCheckBox.Location = new Point(122, 197);
            mondayCheckBox.Name = "mondayCheckBox";
            mondayCheckBox.Size = new Size(53, 19);
            mondayCheckBox.TabIndex = 5;
            mondayCheckBox.Text = "lundi";
            mondayCheckBox.UseVisualStyleBackColor = true;
            mondayCheckBox.Click += Edit;
            // 
            // tuesdayCheckBox
            // 
            tuesdayCheckBox.AutoSize = true;
            tuesdayCheckBox.Location = new Point(122, 225);
            tuesdayCheckBox.Name = "tuesdayCheckBox";
            tuesdayCheckBox.Size = new Size(57, 19);
            tuesdayCheckBox.TabIndex = 6;
            tuesdayCheckBox.Text = "mardi";
            tuesdayCheckBox.UseVisualStyleBackColor = true;
            tuesdayCheckBox.Click += Edit;
            // 
            // wednesdayCheckBox
            // 
            wednesdayCheckBox.AutoSize = true;
            wednesdayCheckBox.Location = new Point(122, 250);
            wednesdayCheckBox.Name = "wednesdayCheckBox";
            wednesdayCheckBox.Size = new Size(73, 19);
            wednesdayCheckBox.TabIndex = 7;
            wednesdayCheckBox.Text = "mercredi";
            wednesdayCheckBox.UseVisualStyleBackColor = true;
            wednesdayCheckBox.Click += Edit;
            // 
            // thursdayCheckBox
            // 
            thursdayCheckBox.AutoSize = true;
            thursdayCheckBox.Location = new Point(122, 275);
            thursdayCheckBox.Name = "thursdayCheckBox";
            thursdayCheckBox.Size = new Size(52, 19);
            thursdayCheckBox.TabIndex = 8;
            thursdayCheckBox.Text = "jeudi";
            thursdayCheckBox.UseVisualStyleBackColor = true;
            thursdayCheckBox.Click += Edit;
            // 
            // fridayCheckBox
            // 
            fridayCheckBox.AutoSize = true;
            fridayCheckBox.Location = new Point(122, 300);
            fridayCheckBox.Name = "fridayCheckBox";
            fridayCheckBox.Size = new Size(72, 19);
            fridayCheckBox.TabIndex = 9;
            fridayCheckBox.Text = "vendredi";
            fridayCheckBox.UseVisualStyleBackColor = true;
            fridayCheckBox.Click += Edit;
            // 
            // saturdayCheckBox
            // 
            saturdayCheckBox.AutoSize = true;
            saturdayCheckBox.Location = new Point(122, 325);
            saturdayCheckBox.Name = "saturdayCheckBox";
            saturdayCheckBox.Size = new Size(64, 19);
            saturdayCheckBox.TabIndex = 10;
            saturdayCheckBox.Text = "samedi";
            saturdayCheckBox.UseVisualStyleBackColor = true;
            saturdayCheckBox.Click += Edit;
            // 
            // sundayCheckBox
            // 
            sundayCheckBox.AutoSize = true;
            sundayCheckBox.Location = new Point(122, 350);
            sundayCheckBox.Name = "sundayCheckBox";
            sundayCheckBox.Size = new Size(79, 19);
            sundayCheckBox.TabIndex = 11;
            sundayCheckBox.Text = "dimanche";
            sundayCheckBox.UseVisualStyleBackColor = true;
            sundayCheckBox.Click += Edit;
            // 
            // time
            // 
            time.AutoSize = true;
            time.Location = new Point(76, 401);
            time.Name = "time";
            time.Size = new Size(39, 15);
            time.TabIndex = 12;
            time.Text = "Heure";
            // 
            // heureDateTimePicker
            // 
            heureDateTimePicker.Format = DateTimePickerFormat.Time;
            heureDateTimePicker.Location = new Point(122, 397);
            heureDateTimePicker.MaxDate = new DateTime(2100, 12, 31, 0, 0, 0, 0);
            heureDateTimePicker.MinDate = new DateTime(2025, 1, 1, 0, 0, 0, 0);
            heureDateTimePicker.Name = "heureDateTimePicker";
            heureDateTimePicker.RightToLeft = RightToLeft.No;
            heureDateTimePicker.ShowUpDown = true;
            heureDateTimePicker.Size = new Size(67, 23);
            heureDateTimePicker.TabIndex = 13;
            heureDateTimePicker.Value = new DateTime(2025, 1, 1, 6, 45, 0, 0);
            heureDateTimePicker.ValueChanged += Edit;
            // 
            // label1
            // 
            label1.AutoSize = true;
            label1.Location = new Point(368, 12);
            label1.Name = "label1";
            label1.Size = new Size(68, 15);
            label1.TabIndex = 14;
            label1.Text = "URL Spotify";
            // 
            // UrlTextBox
            // 
            UrlTextBox.Location = new Point(442, 9);
            UrlTextBox.Name = "UrlTextBox";
            UrlTextBox.Size = new Size(332, 23);
            UrlTextBox.TabIndex = 17;
            UrlTextBox.Click += Edit;
            // 
            // play1SongCheckBox
            // 
            play1SongCheckBox.AutoSize = true;
            play1SongCheckBox.Location = new Point(442, 51);
            play1SongCheckBox.Name = "play1SongCheckBox";
            play1SongCheckBox.Size = new Size(199, 19);
            play1SongCheckBox.TabIndex = 18;
            play1SongCheckBox.Text = "Pause après la première musique";
            play1SongCheckBox.UseVisualStyleBackColor = true;
            play1SongCheckBox.CheckedChanged += play1SongCheckBox_CheckedChanged;
            play1SongCheckBox.Click += Edit;
            // 
            // playXSongsCheckBox
            // 
            playXSongsCheckBox.AutoSize = true;
            playXSongsCheckBox.Location = new Point(622, 85);
            playXSongsCheckBox.Name = "playXSongsCheckBox";
            playXSongsCheckBox.Size = new Size(152, 19);
            playXSongsCheckBox.TabIndex = 19;
            playXSongsCheckBox.Text = "Pause après X musiques";
            playXSongsCheckBox.UseVisualStyleBackColor = true;
            playXSongsCheckBox.CheckedChanged += playXSongsCheckBox_CheckedChanged;
            playXSongsCheckBox.Click += Edit;
            // 
            // playXSecondsCheckBox
            // 
            playXSecondsCheckBox.AutoSize = true;
            playXSecondsCheckBox.Location = new Point(442, 85);
            playXSecondsCheckBox.Name = "playXSecondsCheckBox";
            playXSecondsCheckBox.Size = new Size(150, 19);
            playXSecondsCheckBox.TabIndex = 20;
            playXSecondsCheckBox.Text = "Pause après X secondes";
            playXSecondsCheckBox.UseVisualStyleBackColor = true;
            playXSecondsCheckBox.CheckedChanged += playXSecondsCheckBox_CheckedChanged;
            playXSecondsCheckBox.Click += Edit;
            // 
            // XSongsOrSecondsTextBox
            // 
            XSongsOrSecondsTextBox.Location = new Point(442, 122);
            XSongsOrSecondsTextBox.Name = "XSongsOrSecondsTextBox";
            XSongsOrSecondsTextBox.Size = new Size(76, 23);
            XSongsOrSecondsTextBox.TabIndex = 21;
            XSongsOrSecondsTextBox.Visible = false;
            XSongsOrSecondsTextBox.Click += Edit;
            // 
            // label2
            // 
            label2.AutoSize = true;
            label2.Location = new Point(422, 125);
            label2.Name = "label2";
            label2.Size = new Size(14, 15);
            label2.TabIndex = 22;
            label2.Text = "X";
            label2.Visible = false;
            // 
            // label3
            // 
            label3.AutoSize = true;
            label3.Location = new Point(384, 167);
            label3.Name = "label3";
            label3.Size = new Size(52, 15);
            label3.TabIndex = 23;
            label3.Text = "Enceinte";
            // 
            // label4
            // 
            label4.AutoSize = true;
            label4.Location = new Point(583, 229);
            label4.Name = "label4";
            label4.Size = new Size(71, 15);
            label4.TabIndex = 24;
            label4.Text = "Volume min";
            label4.Visible = false;
            // 
            // label5
            // 
            label5.AutoSize = true;
            label5.Location = new Point(581, 257);
            label5.Name = "label5";
            label5.Size = new Size(73, 15);
            label5.TabIndex = 25;
            label5.Text = "Volume max";
            label5.Visible = false;
            // 
            // SpeakerNameTextBox
            // 
            SpeakerNameTextBox.Location = new Point(442, 164);
            SpeakerNameTextBox.Name = "SpeakerNameTextBox";
            SpeakerNameTextBox.Size = new Size(106, 23);
            SpeakerNameTextBox.TabIndex = 26;
            SpeakerNameTextBox.Text = "Mezzanine n°2";
            SpeakerNameTextBox.Click += Edit;
            // 
            // shuffleCheckBox
            // 
            shuffleCheckBox.AutoSize = true;
            shuffleCheckBox.Location = new Point(701, 51);
            shuffleCheckBox.Name = "shuffleCheckBox";
            shuffleCheckBox.Size = new Size(73, 19);
            shuffleCheckBox.TabIndex = 27;
            shuffleCheckBox.Text = "Aléatoire";
            shuffleCheckBox.UseVisualStyleBackColor = true;
            shuffleCheckBox.Click += Edit;
            // 
            // progressiveVolumeCheckBox
            // 
            progressiveVolumeCheckBox.AutoSize = true;
            progressiveVolumeCheckBox.Location = new Point(442, 197);
            progressiveVolumeCheckBox.Name = "progressiveVolumeCheckBox";
            progressiveVolumeCheckBox.Size = new Size(207, 19);
            progressiveVolumeCheckBox.TabIndex = 28;
            progressiveVolumeCheckBox.Text = "Augmente le son progressivement";
            progressiveVolumeCheckBox.UseVisualStyleBackColor = true;
            progressiveVolumeCheckBox.CheckedChanged += progressiveVolumeCheckBox_CheckedChanged;
            progressiveVolumeCheckBox.Click += Edit;
            // 
            // minVolumeTextBox
            // 
            minVolumeTextBox.Location = new Point(660, 225);
            minVolumeTextBox.Name = "minVolumeTextBox";
            minVolumeTextBox.Size = new Size(103, 23);
            minVolumeTextBox.TabIndex = 29;
            minVolumeTextBox.Text = "10";
            minVolumeTextBox.Visible = false;
            minVolumeTextBox.Click += Edit;
            // 
            // maxVolumeTextBox
            // 
            maxVolumeTextBox.Location = new Point(660, 254);
            maxVolumeTextBox.Name = "maxVolumeTextBox";
            maxVolumeTextBox.Size = new Size(103, 23);
            maxVolumeTextBox.TabIndex = 30;
            maxVolumeTextBox.Text = "45";
            maxVolumeTextBox.Visible = false;
            maxVolumeTextBox.Click += Edit;
            // 
            // label6
            // 
            label6.AutoSize = true;
            label6.Location = new Point(385, 244);
            label6.Name = "label6";
            label6.Size = new Size(47, 15);
            label6.TabIndex = 31;
            label6.Text = "Volume";
            // 
            // flatVolumeTextBox
            // 
            flatVolumeTextBox.Location = new Point(442, 241);
            flatVolumeTextBox.Name = "flatVolumeTextBox";
            flatVolumeTextBox.Size = new Size(103, 23);
            flatVolumeTextBox.TabIndex = 32;
            flatVolumeTextBox.Text = "35";
            flatVolumeTextBox.Click += Edit;
            // 
            // label7
            // 
            label7.AutoSize = true;
            label7.Location = new Point(312, 290);
            label7.Name = "label7";
            label7.Size = new Size(124, 45);
            label7.TabIndex = 33;
            label7.Text = "Secondes entre\r\nchaque augmentation\r\nde volume";
            label7.TextAlign = ContentAlignment.MiddleCenter;
            label7.Visible = false;
            // 
            // volumeIncreasePauseTextBox
            // 
            volumeIncreasePauseTextBox.Location = new Point(442, 298);
            volumeIncreasePauseTextBox.Name = "volumeIncreasePauseTextBox";
            volumeIncreasePauseTextBox.Size = new Size(103, 23);
            volumeIncreasePauseTextBox.TabIndex = 34;
            volumeIncreasePauseTextBox.Visible = false;
            volumeIncreasePauseTextBox.Click += Edit;
            // 
            // label8
            // 
            label8.AutoSize = true;
            label8.Location = new Point(570, 301);
            label8.Name = "label8";
            label8.Size = new Size(84, 15);
            label8.TabIndex = 35;
            label8.Text = "Augmentation";
            label8.Visible = false;
            // 
            // volumeIncreaseTextBox
            // 
            volumeIncreaseTextBox.Location = new Point(660, 298);
            volumeIncreaseTextBox.Name = "volumeIncreaseTextBox";
            volumeIncreaseTextBox.Size = new Size(103, 23);
            volumeIncreaseTextBox.TabIndex = 36;
            volumeIncreaseTextBox.Visible = false;
            volumeIncreaseTextBox.Click += Edit;
            // 
            // startDateLabel
            // 
            startDateLabel.AutoSize = true;
            startDateLabel.Location = new Point(34, 12);
            startDateLabel.Name = "startDateLabel";
            startDateLabel.Size = new Size(81, 15);
            startDateLabel.TabIndex = 3;
            startDateLabel.Text = "Date de début";
            // 
            // splitContainer1
            // 
            splitContainer1.BorderStyle = BorderStyle.FixedSingle;
            splitContainer1.Location = new Point(0, 0);
            splitContainer1.Name = "splitContainer1";
            // 
            // splitContainer1.Panel1
            // 
            splitContainer1.Panel1.Controls.Add(DeleteAlarmButton);
            splitContainer1.Panel1.Controls.Add(NewAlarmButton);
            // 
            // splitContainer1.Panel2
            // 
            splitContainer1.Panel2.Controls.Add(cancelButton);
            splitContainer1.Panel2.Controls.Add(startDateLabel);
            splitContainer1.Panel2.Controls.Add(volumeIncreaseTextBox);
            splitContainer1.Panel2.Controls.Add(label8);
            splitContainer1.Panel2.Controls.Add(volumeIncreasePauseTextBox);
            splitContainer1.Panel2.Controls.Add(label7);
            splitContainer1.Panel2.Controls.Add(flatVolumeTextBox);
            splitContainer1.Panel2.Controls.Add(label6);
            splitContainer1.Panel2.Controls.Add(maxVolumeTextBox);
            splitContainer1.Panel2.Controls.Add(minVolumeTextBox);
            splitContainer1.Panel2.Controls.Add(progressiveVolumeCheckBox);
            splitContainer1.Panel2.Controls.Add(shuffleCheckBox);
            splitContainer1.Panel2.Controls.Add(SpeakerNameTextBox);
            splitContainer1.Panel2.Controls.Add(label5);
            splitContainer1.Panel2.Controls.Add(label4);
            splitContainer1.Panel2.Controls.Add(label3);
            splitContainer1.Panel2.Controls.Add(label2);
            splitContainer1.Panel2.Controls.Add(XSongsOrSecondsTextBox);
            splitContainer1.Panel2.Controls.Add(playXSecondsCheckBox);
            splitContainer1.Panel2.Controls.Add(playXSongsCheckBox);
            splitContainer1.Panel2.Controls.Add(play1SongCheckBox);
            splitContainer1.Panel2.Controls.Add(UrlTextBox);
            splitContainer1.Panel2.Controls.Add(label1);
            splitContainer1.Panel2.Controls.Add(heureDateTimePicker);
            splitContainer1.Panel2.Controls.Add(time);
            splitContainer1.Panel2.Controls.Add(sundayCheckBox);
            splitContainer1.Panel2.Controls.Add(saturdayCheckBox);
            splitContainer1.Panel2.Controls.Add(fridayCheckBox);
            splitContainer1.Panel2.Controls.Add(thursdayCheckBox);
            splitContainer1.Panel2.Controls.Add(wednesdayCheckBox);
            splitContainer1.Panel2.Controls.Add(tuesdayCheckBox);
            splitContainer1.Panel2.Controls.Add(mondayCheckBox);
            splitContainer1.Panel2.Controls.Add(daysOfTheWeek);
            splitContainer1.Panel2.Controls.Add(startDate);
            splitContainer1.Panel2.Controls.Add(apply);
            splitContainer1.Panel2Collapsed = true;
            splitContainer1.Size = new Size(1284, 560);
            splitContainer1.SplitterDistance = 428;
            splitContainer1.TabIndex = 37;
            // 
            // DeleteAlarmButton
            // 
            DeleteAlarmButton.BackColor = Color.Brown;
            DeleteAlarmButton.FlatAppearance.BorderColor = Color.Red;
            DeleteAlarmButton.FlatStyle = FlatStyle.Flat;
            DeleteAlarmButton.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            DeleteAlarmButton.Location = new Point(3, 508);
            DeleteAlarmButton.Name = "DeleteAlarmButton";
            DeleteAlarmButton.Size = new Size(205, 47);
            DeleteAlarmButton.TabIndex = 38;
            DeleteAlarmButton.Text = "Supprimer";
            DeleteAlarmButton.UseVisualStyleBackColor = false;
            DeleteAlarmButton.Visible = false;
            DeleteAlarmButton.Click += button2_Click;
            // 
            // NewAlarmButton
            // 
            NewAlarmButton.BackColor = Color.PaleGreen;
            NewAlarmButton.FlatAppearance.BorderColor = Color.Lime;
            NewAlarmButton.FlatStyle = FlatStyle.Flat;
            NewAlarmButton.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            NewAlarmButton.Location = new Point(218, 508);
            NewAlarmButton.Name = "NewAlarmButton";
            NewAlarmButton.Size = new Size(205, 47);
            NewAlarmButton.TabIndex = 37;
            NewAlarmButton.Text = "Nouveau";
            NewAlarmButton.UseVisualStyleBackColor = false;
            NewAlarmButton.Click += NewAlarmButton_Click;
            // 
            // cancelButton
            // 
            cancelButton.BackColor = Color.Gainsboro;
            cancelButton.FlatAppearance.BorderColor = Color.DarkGray;
            cancelButton.FlatStyle = FlatStyle.Flat;
            cancelButton.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            cancelButton.Location = new Point(469, 508);
            cancelButton.Name = "cancelButton";
            cancelButton.Size = new Size(148, 47);
            cancelButton.TabIndex = 37;
            cancelButton.Text = "Annuler";
            cancelButton.UseVisualStyleBackColor = false;
            cancelButton.Visible = false;
            cancelButton.Click += cancelButton_Click;
            // 
            // Configurator
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(1284, 561);
            Controls.Add(splitContainer1);
            Name = "Configurator";
            Text = "Configurator";
            splitContainer1.Panel1.ResumeLayout(false);
            splitContainer1.Panel2.ResumeLayout(false);
            splitContainer1.Panel2.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)splitContainer1).EndInit();
            splitContainer1.ResumeLayout(false);
            ResumeLayout(false);
        }

        #endregion
        private Button apply;
        private MonthCalendar startDate;
        private Label daysOfTheWeek;
        private CheckBox mondayCheckBox;
        private CheckBox tuesdayCheckBox;
        private CheckBox wednesdayCheckBox;
        private CheckBox thursdayCheckBox;
        private CheckBox fridayCheckBox;
        private CheckBox saturdayCheckBox;
        private CheckBox sundayCheckBox;
        private Label time;
        private DateTimePicker heureDateTimePicker;
        private Label label1;
        private TextBox UrlTextBox;
        private CheckBox play1SongCheckBox;
        private CheckBox playXSongsCheckBox;
        private CheckBox playXSecondsCheckBox;
        private TextBox XSongsOrSecondsTextBox;
        private Label label2;
        private Label label3;
        private Label label4;
        private Label label5;
        private TextBox SpeakerNameTextBox;
        private CheckBox shuffleCheckBox;
        private CheckBox progressiveVolumeCheckBox;
        private TextBox minVolumeTextBox;
        private TextBox maxVolumeTextBox;
        private Label label6;
        private TextBox flatVolumeTextBox;
        private Label label7;
        private TextBox volumeIncreasePauseTextBox;
        private Label label8;
        private TextBox volumeIncreaseTextBox;
        private Label startDateLabel;
        private SplitContainer splitContainer1;
        private Button DeleteAlarmButton;
        private Button NewAlarmButton;
        private Button cancelButton;
    }
}
