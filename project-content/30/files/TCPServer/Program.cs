using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public class TcpServer
{
    private TcpListener server;
    private Thread serverThread;

    public TcpServer()
    {
        server = new TcpListener(IPAddress.Any, 5000);
        serverThread = new Thread(new ThreadStart(StartServer));
        serverThread.IsBackground = true;
        serverThread.Start();
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

        // Créer un nouveau formulaire pour chaque client
        ClientForm clientForm = new ClientForm(client, stream);
        clientForm.FormClosed += (sender, e) =>
        {
            client.Close();
        };
        Application.Run(clientForm);
    }

    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        TcpServer server = new TcpServer();
        Application.Run(new Form()); // Garder l'application en cours d'exécution
    }
}

public class ClientForm : Form
{
    public TcpClient client;
    public NetworkStream stream;
    private TextBox messageBox;
    private Button sendButton;
    private TextBox chatBox;
    private Thread readThread;

    public ClientForm(TcpClient client, NetworkStream stream)
    {
        this.client = client;
        this.stream = stream;

        this.Text = "Client Chat";
        this.Size = new System.Drawing.Size(400, 300);

        chatBox = new TextBox() { Left = 10, Top = 10, Width = 360, Height = 200, Multiline = true, ReadOnly = true };
        messageBox = new TextBox() { Left = 10, Top = 220, Width = 260 };
        sendButton = new Button() { Text = "Send", Left = 280, Top = 220, Width = 90 };
        sendButton.Click += new EventHandler(SendButton_Click);

        this.Controls.Add(chatBox);
        this.Controls.Add(messageBox);
        this.Controls.Add(sendButton);

        readThread = new Thread(ReadMessages);
        readThread.IsBackground = true;
        readThread.Start();
    }

    private void SendButton_Click(object sender, EventArgs e)
    {
        string message = messageBox.Text;
        byte[] data = AesEncryption.Encrypt(message);
        stream.Write(data, 0, data.Length);
        chatBox.AppendText("Server: " + message + Environment.NewLine);
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
                string message = AesEncryption.Decrypt(data);
                this.Invoke((MethodInvoker)delegate
                {
                    chatBox.AppendText("Client: " + message + Environment.NewLine);
                });
            }
            throw new Exception();
        }
        catch (Exception)
        {
            try
            {
                this.Invoke((MethodInvoker)delegate
                {
                    chatBox.AppendText("Client s'est déconnecté." + Environment.NewLine);
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

}
