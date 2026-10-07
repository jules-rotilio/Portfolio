using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public class Peer : Form
{
    private TcpListener server;
    private Thread serverThread;
    private TcpClient client;
    private NetworkStream stream;
    private TextBox messageBox;
    private Button sendButton;
    private TextBox chatBox;
    private TextBox keyBox;
    private TextBox ivBox;
    private Thread readThread;
    private bool clientDisconnected = false;
    private string key;
    private string iv;
    private ConfigForm configForm;

    public Peer(string ipAddress, int peerPort, int ownPort, string key, string iv, ConfigForm configForm)
    {
        this.key = key;
        this.iv = iv;
        this.configForm = configForm;
        // if build is debug: string is P2P Chat (debug)
#if DEBUG
        this.Text = "P2P Chat (debug)";
#else
            this.Text = "P2P Chat";
#endif

        this.Size = new System.Drawing.Size(400, 300);

        chatBox = new TextBox() { Left = 10, Top = 10, Width = 360, Height = 200, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical };
        messageBox = new TextBox() { Left = 10, Top = 220, Width = 260 };
        messageBox.KeyDown += new KeyEventHandler(MessageBox_KeyDown);
        sendButton = new Button() { Text = "Send", Left = 280, Top = 220, Width = 90 };
        sendButton.Click += new EventHandler(SendButton_Click);

        this.Controls.Add(chatBox);
        this.Controls.Add(messageBox);
        this.Controls.Add(sendButton);

        // Démarrer le serveur
        server = new TcpListener(IPAddress.Any, ownPort);
        serverThread = new Thread(new ThreadStart(StartServer));
        serverThread.IsBackground = true;
        serverThread.Start();

        // Se connecter à un autre pair
        client = new TcpClient(ipAddress, peerPort);
        stream = client.GetStream();

        this.FormClosed += (sender, e) =>
        {
            client.Close();
            configForm.Close();
        };

        readThread = new Thread(ReadMessages);
        readThread.IsBackground = true;
        readThread.Start();
    }

    private void StartServer()
    {
        server.Start();
        while (true)
        {
            TcpClient client = server.AcceptTcpClient();
            Thread clientThread = new Thread(new ParameterizedThreadStart(HandleClient));
            clientThread.IsBackground = true;
            clientThread.Start(client);
        }
    }

    private void HandleClient(object clientObj)
    {
        TcpClient client = (TcpClient)clientObj;
        NetworkStream stream = client.GetStream();

        byte[] buffer = new byte[1024];
        int bytesRead;

        try
        {
            while ((bytesRead = stream.Read(buffer, 0, buffer.Length)) != 0)
            {
                byte[] data = new byte[bytesRead];
                Array.Copy(buffer, data, bytesRead);
                string message = AesEncryption.Decrypt(data, key, iv);
                this.Invoke((MethodInvoker)delegate
                {
                    chatBox.AppendText("Peer: " + message + Environment.NewLine);
                });
            }
        }
        catch (Exception)
        {
            try
            {
                this.Invoke((MethodInvoker)delegate
                {
                    chatBox.AppendText("Peer s'est déconnecté." + Environment.NewLine);
                });
            }
            catch (Exception)
            {
                // client form closed
            }
        }
        finally
        {
            client.Close();
        }
    }

    private void SendButton_Click(object sender, EventArgs e)
    {
        string message = messageBox.Text;
        if (message == "" || clientDisconnected)
        {
            return;
        }
        byte[] data = AesEncryption.Encrypt(message, key, iv);
        stream.Write(data, 0, data.Length);
        chatBox.AppendText("You: " + message + Environment.NewLine);
        messageBox.Clear();
    }

    private void ReadMessages()
    {
        byte[] buffer = new byte[1024];
        int bytesRead;

        try
        {
            while ((bytesRead = stream.Read(buffer, 0, buffer.Length)) != 0)
            {
                byte[] data = new byte[bytesRead];
                Array.Copy(buffer, data, bytesRead);
                string message = AesEncryption.Decrypt(data, key, iv);
                this.Invoke((MethodInvoker)delegate
                {
                    chatBox.AppendText("Peer: " + message + Environment.NewLine);
                });
            }
        }
        catch (Exception)
        {
            clientDisconnected = true;
            try
            {
                this.Invoke((MethodInvoker)delegate
                {
                    chatBox.AppendText("Peer s'est déconnecté." + Environment.NewLine);
                });
            }
            catch (Exception)
            {
                // client form closed
            }
        }
        finally
        {
            client.Close();
        }
    }

    private void MessageBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Enter)
        {
            e.SuppressKeyPress = true; // Empêche le son de la touche "Entrée"
            SendButton_Click(sender, e);
        }
    }
}
