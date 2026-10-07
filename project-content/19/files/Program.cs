using MimeKit;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Security;


namespace TestClient
{
	public class Program
	{
		static string ConvertSecureStringToString(SecureString secureString)
		{
			IntPtr unmanagedString = IntPtr.Zero;
			try
			{
				unmanagedString = Marshal.SecureStringToGlobalAllocUnicode(secureString);
				return Marshal.PtrToStringUni(unmanagedString);
			}
			finally
			{
				Marshal.ZeroFreeGlobalAllocUnicode(unmanagedString);
			}
		}
		static SecureString GetPassword()
		{
			SecureString password = new();
			string test = "";
			Console.WriteLine("Enter password: ");

			ConsoleKeyInfo nextKey = Console.ReadKey(true);

			while (nextKey.Key != ConsoleKey.Enter)
			{
				if (nextKey.Key == ConsoleKey.Backspace)
				{
					if (password.Length > 0)
					{
						password.RemoveAt(password.Length - 1);
						// erase the last * as well
						Console.Write(nextKey.KeyChar);
						Console.Write(" ");
						Console.Write(nextKey.KeyChar);
					}
				}
				else
				{
					test += nextKey.KeyChar;
					password.AppendChar(nextKey.KeyChar);
					Console.Write("*");
				}
				nextKey = Console.ReadKey(true);
			}
			
			Console.WriteLine();
			Console.WriteLine(test);
			password.MakeReadOnly();
			return password;
		}

		static void Disp_Help()
		{
			Console.Error.WriteLine(@"
Program written in C# by Jules ROTILIO.

Aide :
\tUtilisez -To pour renseinger l'e-mail du destinataire
\tUtilisez -From pour renseinger l'e-mail de l'emmeteur
\tUtilisez -HTMLFile pour renseinger l'emplacement du fichier contenant le mail sous forme html
\tUtilisez -MailString pour renseinger le contenu du mail
\tUtilisez -NoHTML pour indiquer que le corps du mail est vide
\tUtilisez -Subject pour renseinger l'objet de l'email
\tUtilisez -Files pour renseinger l'emplacement du/des fichier(s) à joindre
\t\tPour utiliser plusieurs fichiers, il faut les séparer d'une virgule
".Replace("\\t", "\t"));
			//\tUtilisez -Password pour renseinger votre mdp (en cas d'authentification)
			return;
		}

		static void Main(string[] args)
		{
			string smtpserver = "";
			string subject = "";
			SecureString password;
			string htmlfile = "";
			string from = "";
			string to = "";
			string mailstring = "";
			bool flag_htmlfile = false, flag_mailstring = false, nohtml = false;

			string pre_em = "";
			string nom_em = "";
			string pre_de = "";
			string nom_de = "";


			if (args.Length == 0) { Disp_Help(); return; }
			for (int i = 0; i < args.Length; i++)
			{
				string argument = args[i];
				if (argument == "--help")
				{
					Disp_Help();
					return;
				}
				try
				{
					string nextarg = args[i + 1];
					switch (argument.ToLower())
					{
						case "-from":
							if (nextarg.StartsWith("-")) { Disp_Help(); return; }
							from = nextarg;
							pre_em = from.Split(".")[0];
							nom_em = from.Split(".")[1];
							i++;
							break;
						case "-to":
							if (nextarg.StartsWith("-")) { Disp_Help(); return; }
							to = nextarg;
							pre_de = to.Split(".")[0];
							nom_de = to.Split(".")[1];
							i++;
							break;
						case "-htmlfile":
							if (nextarg.StartsWith("-") || flag_mailstring || nohtml) { Disp_Help(); return; }
							htmlfile = File.ReadAllText(nextarg);
							flag_htmlfile = true;
							i++;
							break;
						case "-mailstring":
							if (nextarg.StartsWith("-") || flag_htmlfile || nohtml) { Disp_Help(); return; }
							mailstring = nextarg;
							Console.WriteLine(mailstring);
							flag_mailstring = true;
							i++;
							break;
						case "-subject":
							if (nextarg.StartsWith("-")) { Disp_Help(); return; }
							subject = nextarg;
							i++;
							break;
						case "-nohtml":
							nohtml = true;
							break;
						case "-files":
							break;
						default:
							Console.WriteLine(string.Format("invalid argument : '{0}'", argument));
							Environment.Exit(1);
							break;
					}
				}
				catch (System.IndexOutOfRangeException) { Disp_Help(); return; }
			}


			Console.WriteLine("password please");
			password = GetPassword();
			Console.WriteLine();
			Console.WriteLine("thanks");
			string domain = from.Split("@")[1];
			Console.WriteLine(from);
			Console.WriteLine(from.Split("@")[1]);

			switch (domain)
			{
				case "supinfo.com":
					smtpserver = "smtp.office365.com";
					break;
				case "gmail.com":
					smtpserver = "smtp.gmail.com";
					break;
				default:
					Console.WriteLine(domain);
					Console.Error.WriteLine("connais pas votre serveur smtp");
					Environment.Exit(2);
					break;
			}


			var message = new MimeMessage();
			message.From.Add(new MailboxAddress(pre_em + " " + nom_em, from));
			message.To.Add(new MailboxAddress(pre_de + " " + nom_de, to));
			message.Subject = subject;
			MimeEntity body;
			if (nohtml)
			{
				body = new BodyBuilder().ToMessageBody();
			}
			else if (flag_htmlfile)
			{
				body = new BodyBuilder() { HtmlBody = htmlfile }.ToMessageBody();
			}
			else if (flag_mailstring)
			{
				body = new BodyBuilder() { TextBody = mailstring }.ToMessageBody();
			}
			else
			{
				body = new TextPart();
				Console.Error.WriteLine("faut choisir une option : nothml, htmlfile ou mailstring");
				Environment.Exit(2);
			}
			message.Body = body;

			using MailKit.Net.Smtp.SmtpClient client = new();
			if (password.Length < 0)
			{
				//587-465
				client.Connect(smtpserver, 587, MailKit.Security.SecureSocketOptions.StartTls);
				Console.WriteLine(client.IsConnected);
				client.Authenticate(from, ConvertSecureStringToString(password));
			}
			else
			{
				client.Connect(smtpserver, 25, false);
			}
			client.Send(message);
			client.Disconnect(true);
			client.Dispose();
		}
	}
}

