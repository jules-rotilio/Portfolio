using System;
using System.Diagnostics;
using System.Management.Automation;
using MimeKit;
using MailKit;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Security;
using System.Runtime.Serialization;
using System.Security.Authentication;
using System.Net.Sockets;

#pragma warning disable 8618

namespace MailKitModule
{
	public class AuthException : Exception
	{
		public AuthException() { }

		public AuthException(string message)
			: base(message) { }


		public AuthException(string? message, Exception? innerException)
			: base(message, innerException) { }

		protected AuthException(SerializationInfo info, StreamingContext context)
			: base(info, context) { }
	}
	public class ConnException : Exception
	{
		public ConnException() { }

		public ConnException(string message)
			: base(message) { }


		public ConnException(string? message, Exception? innerException)
			: base(message, innerException) { }

		protected ConnException(SerializationInfo info, StreamingContext context)
			: base(info, context) { }
	}

	[Cmdlet(VerbsCommunications.Send, "MailKitMail")]
	public class SendMailKitMailCommand : PSCmdlet
	{
		

		private readonly MimeMessage message = new();

		private readonly MailKit.Net.Smtp.SmtpClient client = new();

		private readonly BodyBuilder bodyBuilder = new();

		// public Object InputObject { get; set; }


		[Parameter(Position = 0, Mandatory = true)]
		public required String From { get; set; }

		[Parameter(Position = 1, Mandatory = true)]
		public required String To { get; set; }

		[Parameter(Position = 2, Mandatory = true)]
		public PSCredential Credential { get; set; }

		[Parameter(Position = 3, Mandatory = true)]
		public String Subject { get; set; }

		[Parameter(Position = 4, Mandatory = true, ParameterSetName = "HTMLMAIL")]
		public String HTMLFile { get; set; }

		[Parameter(Position = 4, Mandatory = true, ParameterSetName = "STRINGMAIL")]
		public String MailString { get; set; }

		[Parameter(Position = 4, Mandatory = true, ParameterSetName = "NOBODY")]
		public SwitchParameter NoHTML { get; set; } = false;

		[Parameter(Position = 5, Mandatory = true)]
		public String SMTPServer { get; set; }

		[Parameter(Position = 6, Mandatory = true)]
		public int SMTPPort { get; set; }

		[Parameter(Mandatory = false)]
		public Array Files { get; set; }

		protected override void BeginProcessing()
		{
			message.From.Add(new MailboxAddress(From, From));
			message.To.Add(new MailboxAddress(To, To));
			message.Subject = Subject;

			try
			{

				client.Connect(SMTPServer, SMTPPort, MailKit.Security.SecureSocketOptions.Auto);
				if (!client.IsConnected)
				{
					throw new ConnException("Client is not connected");
				}
				client.Authenticate(From, Credential.GetNetworkCredential().Password);
				if (!client.IsAuthenticated)
				{
					throw new AuthException("Client is not authenticated");
				}
			}
			catch (Exception e)
			{
                ErrorCategory errorCategory;
				String errorID;

				switch (e){
					case AuthenticationException:
						errorCategory = ErrorCategory.AuthenticationError;
						errorID = "AuthenticationError";
						break;
					case SocketException:
						errorCategory = ErrorCategory.ConnectionError;
						errorID = "ConnectionError";
						break;
					default :
						errorCategory = ErrorCategory.NotImplemented;
						errorID = "NotImplemented";
						break;
				}

                var errorRecord = new ErrorRecord(
					e,
					errorID,
					errorCategory,
					this
				);

				ThrowTerminatingError(errorRecord);
			}
		}
		protected override void ProcessRecord()
		{
			/*
			message.Body = ParameterSetName switch
            {
                "HTMLMAIL" => new TextPart("html")
                {
                    Text = File.ReadAllText(HTMLFile)
                },
                "STRINGMAIL" => new TextPart("plain")
                {
                    Text = MailString
                },
                "NOBODY" => null,
                _ => throw new Exception("something went wrong"),
            };
			*/
			switch (ParameterSetName)
			{
				case "HTMLMAIL":
					bodyBuilder.HtmlBody = File.ReadAllText(HTMLFile);
					break;
				case "STRINGMAIL":
					bodyBuilder.TextBody = MailString;
					break;
				case "NOBODY":
					break;
				default:
					throw new Exception("something went wrong");

			}

			message.Body = bodyBuilder.ToMessageBody();


			if (client.IsAuthenticated)
			{
				client.Send(message);
			}
		}
		protected override void EndProcessing()
		{
			base.EndProcessing();
			client.Disconnect(true);
			client.Dispose();
		}
	}
}
