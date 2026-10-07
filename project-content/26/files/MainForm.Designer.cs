namespace ShowMicVolume
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;
        private ProgressBar progressBar;
        private ProgressBar progressBar2; // Nouvelle barre de progression pour le deuxième périphérique
        private Label label1; // Label pour le premier microphone
        private Label label2; // Label pour le deuxième microphone
        private Label statusLabel; // Nouveau label pour le statut
        //private Label debuglabel;

        #region Windows Form Designer generated code
        private void InitializeComponent()
        {
            this.progressBar = new VerticalNoAnimationProgressBar { Minimum = 0, Maximum = 100, Width = 50, Height = 200 };
            this.progressBar2 = new VerticalNoAnimationProgressBar { Minimum = 0, Maximum = 100, Width = 50, Height = 200 }; // Initialisation de la nouvelle barre de progression
            this.label1 = new Label { Width = 200 }; // Initialisation du label pour le premier microphone
            this.label1.AutoSize = true;
            this.label2 = new Label { Width = 200 }; // Initialisation du label pour le deuxième microphone
            this.label2.AutoSize = true;
            this.statusLabel = new Label { Width = 200 }; // Initialisation du nouveau label
            this.statusLabel.AutoSize = true;

            // this.debuglabel = new Label { Width = 200 };
            // this.debuglabel.AutoSize = true;

            this.Controls.Add(this.progressBar);
            this.Controls.Add(this.progressBar2); // Ajout de la nouvelle barre de progression aux contrôles
            this.Controls.Add(this.label1); // Ajout du label pour le premier microphone aux contrôles
            this.Controls.Add(this.label2); // Ajout du label pour le deuxième microphone aux contrôles
            this.Controls.Add(this.statusLabel); // Ajout du nouveau label aux contrôles
            // this.Controls.Add(this.debuglabel);

            this.Width = 300; // Augmentation de la largeur pour les deux barres de progression
            this.Height = 330; // Augmentation de la hauteur pour les nouveaux labels
            this.Load += new System.EventHandler(this.MainForm_Load);
            this.TopMost = true;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.MinimizeBox = false;

            this.Icon = Resource.microphone;
        }
        #endregion
    }
}
