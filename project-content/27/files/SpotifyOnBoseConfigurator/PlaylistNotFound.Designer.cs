namespace SpotifyOnBoseConfigurator
{
    partial class PlaylistNotFound
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
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
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            playlistNotFoundTitleLabel = new Label();
            playlistNotFoundTitle2Label = new Label();
            playlistNameTextBox = new TextBox();
            validerButton = new Button();
            annulerButton = new Button();
            SuspendLayout();
            // 
            // playlistNotFoundTitleLabel
            // 
            playlistNotFoundTitleLabel.AutoSize = true;
            playlistNotFoundTitleLabel.Font = new Font("Segoe UI", 30F);
            playlistNotFoundTitleLabel.Location = new Point(12, 9);
            playlistNotFoundTitleLabel.Name = "playlistNotFoundTitleLabel";
            playlistNotFoundTitleLabel.Size = new Size(545, 54);
            playlistNotFoundTitleLabel.TabIndex = 0;
            playlistNotFoundTitleLabel.Text = "La playlist n'a pas été trouvée";
            // 
            // playlistNotFoundTitle2Label
            // 
            playlistNotFoundTitle2Label.AutoSize = true;
            playlistNotFoundTitle2Label.Font = new Font("Segoe UI", 20.25F, FontStyle.Regular, GraphicsUnit.Point, 0);
            playlistNotFoundTitle2Label.Location = new Point(12, 95);
            playlistNotFoundTitle2Label.Name = "playlistNotFoundTitle2Label";
            playlistNotFoundTitle2Label.Size = new Size(696, 37);
            playlistNotFoundTitle2Label.TabIndex = 1;
            playlistNotFoundTitle2Label.Text = "Si toutefois la playlist existe, alors renseignez son nom ici:";
            // 
            // playlistNameTextBox
            // 
            playlistNameTextBox.Font = new Font("Segoe UI", 20F);
            playlistNameTextBox.Location = new Point(62, 179);
            playlistNameTextBox.Name = "playlistNameTextBox";
            playlistNameTextBox.Size = new Size(663, 43);
            playlistNameTextBox.TabIndex = 2;
            // 
            // validerButton
            // 
            validerButton.BackColor = Color.PaleGreen;
            validerButton.FlatAppearance.BorderColor = Color.Lime;
            validerButton.FlatStyle = FlatStyle.Flat;
            validerButton.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            validerButton.Location = new Point(583, 391);
            validerButton.Name = "validerButton";
            validerButton.Size = new Size(205, 47);
            validerButton.TabIndex = 38;
            validerButton.Text = "Valider";
            validerButton.UseVisualStyleBackColor = false;
            // 
            // annulerButton
            // 
            annulerButton.BackColor = Color.Brown;
            annulerButton.FlatAppearance.BorderColor = Color.Red;
            annulerButton.FlatStyle = FlatStyle.Flat;
            annulerButton.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            annulerButton.Location = new Point(12, 391);
            annulerButton.Name = "annulerButton";
            annulerButton.Size = new Size(205, 47);
            annulerButton.TabIndex = 39;
            annulerButton.Text = "Annuler";
            annulerButton.UseVisualStyleBackColor = false;
            // 
            // PlaylistNotFound
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(800, 450);
            Controls.Add(annulerButton);
            Controls.Add(validerButton);
            Controls.Add(playlistNameTextBox);
            Controls.Add(playlistNotFoundTitle2Label);
            Controls.Add(playlistNotFoundTitleLabel);
            Name = "PlaylistNotFound";
            Text = "PlaylistNotFound";
            ResumeLayout(false);
            PerformLayout();
        }

        #endregion

        private Label playlistNotFoundTitleLabel;
        private Label playlistNotFoundTitle2Label;
        private TextBox playlistNameTextBox;
        private Button validerButton;
        private Button annulerButton;
    }
}