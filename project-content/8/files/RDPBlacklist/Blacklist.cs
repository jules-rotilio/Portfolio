using System;
using System.Collections.Generic;
using System.Data;
using System.Data.SQLite;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;

class Program
{
	static void Main()
	{
		Blacklist blacklist = new();

		// Démarrer la surveillance des événements de journalisation
		blacklist.StartEventLogMonitoring();

		// Planifiez une tâche périodique pour mettre à jour les règles du pare-feu
		Timer timer = new(blacklist.UpdateFirewallRules, null, TimeSpan.Zero, TimeSpan.FromMinutes(5));

		Console.WriteLine("En attente d'événements de journalisation RDP. Appuyez sur Entrée pour quitter.");
		Console.ReadLine();
	}
}

class Blacklist
{
	public Blacklist()
	{
		// Création ou ouverture de la base de données SQLite
		connection = new(connectionString);
		connection.Open();

		InitTables();


	}

	readonly SQLiteConnection connection;
	static readonly string logName = "Security";
	static readonly string sourceName = "Microsoft-Windows-Security-Auditing";
	static readonly string connectionString = "Data Source=I:\\dotnet projets\\SecuriteRDP\\mydatabase.db;Version=3;";
	void InitTables()
	{
		// Création des tables si elles n'existent pas
		CreateTable("blacklist", "ip TEXT");
		CreateTable("whitelist", "ip TEXT, raison TEXT");
		CreateTable("attempts", "ip TEXT, timestamp DATETIME");
	}
	void CreateTable(string tableName, string columns)
	{
		string createTableSQL = $"CREATE TABLE IF NOT EXISTS {tableName} ({columns})";
		using SQLiteCommand command = new(createTableSQL, connection);
		command.ExecuteNonQuery();
	}
	public void StartEventLogMonitoring()
	{
		EventLog eventLog = new(logName)
		{
			Source = sourceName
		};

		eventLog.EntryWritten += (sender, e) =>
		{
			if (e.Entry.InstanceId == 4625)
			{
				string? ipAddress = GetIpAddressFromEventLog(e.Entry.Message);
				if (ipAddress != null)
				{
					string logMessage = $"Tentative de connexion RDP échouée depuis {ipAddress}";
					LogMessageToFile(logMessage);

					if (!QueryIsIPWhitelisted(ipAddress))
					{
						InsertIPAttempt(ipAddress);
						if (QueryShouldIPBeBlacklisted(ipAddress))
						{
							InsertIPBlacklist(ipAddress);
							UpdateFirewallRule(ipAddress, block: true);
							LogMessageToFile($"IP {ipAddress} a été blacklistée.");
						}
					}
				}
			}
		};

		eventLog.EnableRaisingEvents = true;
	}

	static string? GetIpAddressFromEventLog(string logMessage)
	{
		const string ipAddressMarker = "Adresse du réseau source :";

		int ipAddressIndex = logMessage.IndexOf(ipAddressMarker);

		if (ipAddressIndex >= 0)
		{
			string ipAddressSubstring = logMessage[(ipAddressIndex + ipAddressMarker.Length)..];
			int endIndex = ipAddressSubstring.IndexOfAny(new char[] { ' ', '\r', '\n' });

			if (endIndex >= 0)
			{
				string ipAddress = ipAddressSubstring[..endIndex].Trim();
				return ipAddress;
			}
		}

		return null;
	}

	static void LogMessageToFile(string logMessage)
	{
		// Spécifiez le chemin du fichier de log
		string logFilePath = "log.txt";

		// Utilisez StreamWriter pour écrire dans le fichier de log
		using StreamWriter writer = File.AppendText(logFilePath);
		writer.WriteLine(logMessage);
	}
	bool QueryIsIPWhitelisted(string ip)
	{
		string query = "SELECT COUNT(*) FROM whitelist WHERE ip = @ip";
		using SQLiteCommand command = new(query, connection);
		command.Parameters.AddWithValue("@ip", ip);
		long count = (long)command.ExecuteScalar();
		return count > 0;
	}
	void InsertIPAttempt(string ip)
	{
		string insertQuery = "INSERT INTO attempts (ip, timestamp) VALUES (@ip, @timestamp)";
		using SQLiteCommand command = new(insertQuery, connection);
		command.Parameters.AddWithValue("@ip", ip);
		command.Parameters.AddWithValue("@timestamp", DateTime.Now);
		command.ExecuteNonQuery();
	}
	bool QueryShouldIPBeBlacklisted(string ip)
	{
		DateTime twentyMinutesAgo = DateTime.Now.AddMinutes(-20);
		string checkAttemptsQuery = "SELECT COUNT(*) FROM attempts WHERE ip = @ip AND timestamp > @timestamp";
		using SQLiteCommand command = new(checkAttemptsQuery, connection);
		command.Parameters.AddWithValue("@ip", ip);
		command.Parameters.AddWithValue("@timestamp", twentyMinutesAgo);
		long count = (long)command.ExecuteScalar();
		return count >= 10;
	}
	void InsertIPBlacklist(string ip)
	{
		// Vérifiez d'abord si l'adresse IP n'est pas dans la liste noire
		if (!QueryIsIPBlacklisted(ip) & QueryIsIPWhitelisted(ip))
		{
			string insertQuery = "INSERT INTO blacklist (ip) VALUES (@ip)";
			using SQLiteCommand command = new(insertQuery, connection);
			command.Parameters.AddWithValue("@ip", ip);
			command.ExecuteNonQuery();
		}
	}
	bool QueryIsIPBlacklisted(string ip)
	{
		string query = "SELECT COUNT(*) FROM blacklist WHERE ip = @ip";
		using SQLiteCommand command = new(query, connection);
		command.Parameters.AddWithValue("@ip", ip);
		long count = (long)command.ExecuteScalar();
		return count > 0;
	}
	public void UpdateFirewallRules(object? _)
	{
		List<string> blacklistedIPs = QueryAllBlacklistedIPs();

		foreach (string ip in blacklistedIPs)
		{
			UpdateFirewallRule(ip, block: true);
		}
	}
	List<string> QueryAllBlacklistedIPs()
	{
		List<string> blacklistedIPs = new();

		string query = "SELECT ip FROM blacklist";
		using (SQLiteCommand command = new(query, connection))
		{
			using SQLiteDataReader reader = command.ExecuteReader();
			while (reader.Read())
			{
				string ip = reader.GetString(0);
				blacklistedIPs.Add(ip);
			}
		}

		return blacklistedIPs;
	}
	static void UpdateFirewallRule(string ip, bool block)
	{
		string ruleName = $"Block RDP {ip}";

		Process process = new();
		process.StartInfo.FileName = "netsh";
		process.StartInfo.Arguments = $"advfirewall firewall set rule name=\"{ruleName}\" dir=in new enable={block}";
		process.StartInfo.UseShellExecute = false;
		process.StartInfo.RedirectStandardOutput = true;
		process.StartInfo.RedirectStandardError = true;
		process.Start();
		process.WaitForExit();

		int exitCode = process.ExitCode;
		process.Close();

		if (exitCode == 0)
		{
			string action = block ? "bloqué" : "débloqué";
			Console.WriteLine($"La règle de pare-feu pour l'IP {ip} a été mise à jour pour {action} le trafic RDP.");
		}
		else
		{
			Console.WriteLine($"Erreur lors de la mise à jour de la règle de pare-feu pour l'IP {ip}.");
		}
	}

}

class FirewallRule
{
	public string Name { get; set; } = "";
	public string Description { get; set; } = "";
	public bool Enabled { get; set; }
	public string Direction { get; set; } = "";
	public string Action { get; set; } = "";
	// Add more properties as needed for your use case
}
class NetshOutput
{
	public string Output { get; set; } = "";
	public int ExitCode { get; set; }
}
class Firewall
{

	public static FirewallRule? GetFirewallRule(string ruleName)
	{
		NetshOutput result = ExecuteNetshCommand($"advfirewall firewall show rule name=\"{ruleName}\"");

		if (string.IsNullOrWhiteSpace(result.Output))
		{
			return null; // Rule not found
		}

		// Parse the rule information
		string[] lines = result.Output.Split('\n', StringSplitOptions.RemoveEmptyEntries);
		FirewallRule rule = new();

		foreach (string line in lines)
		{
			string[] parts = line.Split(':');
			if (parts.Length == 2)
			{
				string key = parts[0].Trim();
				string value = parts[1].Trim();

				switch (key)
				{
					case "Name":
						rule.Name = value;
						break;
					case "Description":
						rule.Description = value;
						break;
					case "Enabled":
						rule.Enabled = value.Equals("Yes", StringComparison.OrdinalIgnoreCase);
						break;
					case "Direction":
						rule.Direction = value;
						break;
					case "Action":
						rule.Action = value;
						break;
						// Add more cases as needed for other rule properties
				}
			}
		}

		return rule;
	}


	public static void CreateFirewallRule(string ip, bool allow)
	{
		string ruleName = "RDPBlockRule_" + ip;
		string action = allow ? "allow" : "block";

		NetshOutput result = ExecuteNetshCommand(allow
			? $"advfirewall firewall add rule name=\"{ruleName}\" dir=in action=allow protocol=TCP localport=3389 remoteip={ip}"
			: $"advfirewall firewall add rule name=\"{ruleName}\" dir=in action=block protocol=TCP localport=3389 remoteip={ip}");

		if (result.ExitCode == 0)
		{
			string actionText = allow ? "autorisée" : "bloquée";
			Console.WriteLine($"La règle de pare-feu pour l'IP {ip} a été {actionText} pour le trafic RDP.");
		}
		else
		{
			Console.WriteLine($"Erreur lors de la création de la règle de pare-feu pour l'IP {ip}.");
		}
	}



	private static NetshOutput ExecuteNetshCommand(string arguments)
	{
		Process process = new Process
		{
			StartInfo = new ProcessStartInfo
			{
				FileName = "netsh",
				Arguments = arguments,
				UseShellExecute = false,
				RedirectStandardOutput = true,
				CreateNoWindow = true,
				RedirectStandardError = true
			}
		};

		process.Start();
		string output = process.StandardOutput.ReadToEnd();
		process.WaitForExit();
		int exitCode = process.ExitCode;
		process.Close();

		return new NetshOutput { Output = output, ExitCode = exitCode };
	}

}