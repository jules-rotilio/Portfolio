using System;
using System.Collections.Generic;
using System.Data;
using System.Data.SQLite;
using System.Net;
using System.Net.Sockets;
using System.Threading;

class Program
{
	static void Main()
	{
		// Connexion à la base de données SQLite
		string connectionString = "Data Source=mydatabase.db;Version=3;";
		using (SQLiteConnection connection = new SQLiteConnection(connectionString))
		{
			connection.Open();

			// Création des tables si elles n'existent pas
			CreateTable(connection, "blacklist", "ip TEXT");
			CreateTable(connection, "whitelist", "ip TEXT");
			CreateTable(connection, "attempts", "ip TEXT, timestamp DATETIME");

			int port = 3389; // Port RDP par défaut

			TcpListener listener = new TcpListener(IPAddress.Any, port);
			listener.Start();

			Console.WriteLine("Serveur RDP en attente de connexions...");

			while (true)
			{
				TcpClient client = listener.AcceptTcpClient();
				IPEndPoint endPoint = client.Client.RemoteEndPoint as IPEndPoint;

				if (endPoint != null)
				{
					IPAddress clientIP = endPoint.Address;

					if (!IsIPWhitelisted(connection, clientIP))
					{
						if (IsIPBlacklisted(connection, clientIP))
						{
							// Refuser la connexion RDP
							Console.WriteLine($"Connexion refusée depuis {clientIP}");
							client.Close();
						}
						else
						{
							// Autoriser la connexion RDP
							Console.WriteLine($"Connexion autorisée depuis {clientIP}");
							// Ici, vous pouvez gérer la connexion RDP comme nécessaire.

							// Enregistrement de la tentative dans la base de données
							InsertAttempt(connection, clientIP);
						}
					}
					else
					{
						// IP dans la liste blanche, autoriser la connexion
						Console.WriteLine($"Connexion autorisée depuis {clientIP}");
						// Ici, vous pouvez gérer la connexion RDP comme nécessaire.
					}
				}
				else
				{
					Console.WriteLine("Impossible de récupérer l'adresse IP du client.");
				}
			}
		}
	}

	static void CreateTable(SQLiteConnection connection, string tableName, string columns)
	{
		string createTableSQL = $"CREATE TABLE IF NOT EXISTS {tableName} ({columns})";
		using (SQLiteCommand command = new SQLiteCommand(createTableSQL, connection))
		{
			command.ExecuteNonQuery();
		}
	}

	static bool IsIPWhitelisted(SQLiteConnection connection, IPAddress ip)
	{
		string query = "SELECT COUNT(*) FROM whitelist WHERE ip = @ip";
		using (SQLiteCommand command = new SQLiteCommand(query, connection))
		{
			command.Parameters.AddWithValue("@ip", ip.ToString());
			long count = (long)command.ExecuteScalar();
			return count > 0;
		}
	}

	static bool IsIPBlacklisted(SQLiteConnection connection, IPAddress ip)
	{
		string query = "SELECT COUNT(*) FROM blacklist WHERE ip = @ip";
		using (SQLiteCommand command = new SQLiteCommand(query, connection))
		{
			command.Parameters.AddWithValue("@ip", ip.ToString());
			long count = (long)command.ExecuteScalar();
			return count > 0;
		}
	}

	static void InsertAttempt(SQLiteConnection connection, IPAddress ip)
	{
		string insertQuery = "INSERT INTO attempts (ip, timestamp) VALUES (@ip, @timestamp)";
		using (SQLiteCommand command = new SQLiteCommand(insertQuery, connection))
		{
			command.Parameters.AddWithValue("@ip", ip.ToString());
			command.Parameters.AddWithValue("@timestamp", DateTime.Now);
			command.ExecuteNonQuery();
		}

		// Vérification des tentatives infructueuses récentes
		DateTime twentyMinutesAgo = DateTime.Now.AddMinutes(-20);
		string checkAttemptsQuery = "SELECT COUNT(*) FROM attempts WHERE ip = @ip AND timestamp > @timestamp";
		using (SQLiteCommand command = new SQLiteCommand(checkAttemptsQuery, connection))
		{
			command.Parameters.AddWithValue("@ip", ip.ToString());
			command.Parameters.AddWithValue("@timestamp", twentyMinutesAgo);
			long count = (long)command.ExecuteScalar();

			if (count >= 10)
			{
				// Blacklister l'IP
				BlacklistIP(connection, ip);
			}
		}
	}

	static void BlacklistIP(SQLiteConnection connection, IPAddress ip)
	{
		string insertQuery = "INSERT INTO blacklist (ip) VALUES (@ip)";
		using (SQLiteCommand command = new SQLiteCommand(insertQuery, connection))
		{
			command.Parameters.AddWithValue("@ip", ip.ToString());
			command.ExecuteNonQuery();
		}
	}
}
