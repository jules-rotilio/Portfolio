using System;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

public class ConfigForm : Form
{
    private TextBox ipBox;
    private TextBox portBox;
    private TextBox ownPortBox;
    private TextBox keyBox;
    private TextBox ivBox;
    private Button connectButton;
    private Button generateButton;
    private Button copyKeyButton;
    private Button copyIvButton;

    public ConfigForm()
    {
        this.Text = "Configuration";
        this.Size = new System.Drawing.Size(300, 400);

        Label ipLabel = new Label() { Text = "IP du pair:", Left = 10, Top = 20, Width = 100 };
        ipBox = new TextBox() { Left = 120, Top = 20, Width = 150 };

        Label portLabel = new Label() { Text = "Port du pair:", Left = 10, Top = 60, Width = 100 };
        portBox = new TextBox() { Left = 120, Top = 60, Width = 150 };

        Label ownPortLabel = new Label() { Text = "Votre port:", Left = 10, Top = 100, Width = 100 };
        ownPortBox = new TextBox() { Left = 120, Top = 100, Width = 150 };

        Label keyLabel = new Label() { Text = "Clé:", Left = 10, Top = 140, Width = 100 };
        keyBox = new TextBox() { Left = 120, Top = 140, Width = 150 };

        Label ivLabel = new Label() { Text = "IV:", Left = 10, Top = 180, Width = 100 };
        ivBox = new TextBox() { Left = 120, Top = 180, Width = 150 };

        connectButton = new Button() { Text = "Connecter", Left = 100, Top = 220, Width = 100 };
        connectButton.Click += new EventHandler(ConnectButton_Click);

        generateButton = new Button() { Text = "Générer AES+IV", Left = 10, Top = 260, Width = 120 };
        generateButton.Click += new EventHandler(GenerateButton_Click);

        copyKeyButton = new Button() { Text = "Copier Clé", Left = 140, Top = 260, Width = 120 };
        copyKeyButton.Click += new EventHandler(CopyKeyButton_Click);

        copyIvButton = new Button() { Text = "Copier IV", Left = 10, Top = 300, Width = 120 };
        copyIvButton.Click += new EventHandler(CopyIvButton_Click);

        this.Controls.Add(ipLabel);
        this.Controls.Add(ipBox);
        this.Controls.Add(portLabel);
        this.Controls.Add(portBox);
        this.Controls.Add(ownPortLabel);
        this.Controls.Add(ownPortBox);
        this.Controls.Add(keyLabel);
        this.Controls.Add(keyBox);
        this.Controls.Add(ivLabel);
        this.Controls.Add(ivBox);
        this.Controls.Add(connectButton);
        this.Controls.Add(generateButton);
        this.Controls.Add(copyKeyButton);
        this.Controls.Add(copyIvButton);
    }

    private void OpenPeerForm(string ipAddress, int peerPort, int ownPort, string key, string iv)
    {
        Peer chatForm = new Peer(ipAddress, peerPort, ownPort, key, iv, this);
        chatForm.Show();
        this.Hide();
    }

    private void ConnectButton_Click(object sender, EventArgs e)
    {
        string ipAddress = ipBox.Text;
        int peerPort = int.Parse(portBox.Text);
        int ownPort = int.Parse(ownPortBox.Text);
        string key = keyBox.Text;
        string iv = ivBox.Text;

        OpenPeerForm(ipAddress, peerPort, ownPort, key, iv);
    }


    private void GenerateButton_Click(object sender, EventArgs e)
    {
        using (Aes aes = Aes.Create())
        {
            aes.KeySize = 128; // 16 bytes = 128 bits
            aes.GenerateKey();
            aes.GenerateIV();

            keyBox.Text = Convert.ToBase64String(aes.Key);
            ivBox.Text = Convert.ToBase64String(aes.IV);
        }
    }

    private void CopyKeyButton_Click(object sender, EventArgs e)
    {
        Clipboard.SetText(keyBox.Text);
    }

    private void CopyIvButton_Click(object sender, EventArgs e)
    {
        Clipboard.SetText(ivBox.Text);
    }

    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new ConfigForm());
    }
}
