using System;
using System.Net.Sockets;
using System.Text;
using System.Windows.Forms;

public class TcpClientForm : Form
{
    private TextBox messageBox;
    private Button sendButton;
    private TextBox chatBox;
    private TcpClient client;
    private NetworkStream stream;
    private bool clientDisconnected = false;

    public TcpClientForm()
    {
        this.Text = "TCP Client";
        this.Size = new System.Drawing.Size(400, 300);



        chatBox = new TextBox() { Left = 10, Top = 10, Width = 360, Height = 200, Multiline = true, ReadOnly = true };
        messageBox = new TextBox() { Left = 10, Top = 220, Width = 260 };
        sendButton = new Button() { Text = "Send", Left = 280, Top = 220, Width = 90 };
        sendButton.Click += new EventHandler(SendButton_Click);

        this.Controls.Add(chatBox);
        this.Controls.Add(messageBox);
        this.Controls.Add(sendButton);

        client = new TcpClient("127.0.0.1", 5000);
        stream = client.GetStream();

        this.FormClosed += (sender, e) =>
        {
            client.Close();
        };

        Thread readThread = new Thread(ReadMessages);
        readThread.IsBackground = true;
        readThread.Start();
    }

    private void SendButton_Click(object sender, EventArgs e)
    {
        string message = messageBox.Text;
        if (message == "" || clientDisconnected)
        {
            return;
        }
        byte[] data = AesEncryption.Encrypt(message);
        stream.Write(data, 0, data.Length);
        chatBox.AppendText("Client: " + message + Environment.NewLine);
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
                    chatBox.AppendText("Server: " + message + Environment.NewLine);
                });
            }
            throw new Exception();
        }
        catch (Exception)
        {
            clientDisconnected = true;
            this.Invoke((MethodInvoker)delegate
            {
                chatBox.AppendText("Serveur s'est déconnecté." + Environment.NewLine);
            });
        }
        finally
        {
            client.Close();
        }
    }


    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new TcpClientForm());
    }
}
