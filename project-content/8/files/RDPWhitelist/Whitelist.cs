using System;
using System.Data;
using System.Data.SQLite;
using System.Net;

class Program
{
	static readonly string connectionString = "Data Source=I:\\dotnet projets\\SecuriteRDP\\mydatabase.db;Version=3;";

	static void Main()
	{
		using (SQLiteConnection connection = new SQLiteConnection(connectionString))
		{
			connection.Open();

			Console.WriteLine("Programme de whitelisting d'adresses IP.");

			while (true)
			{
				Console.Write("Entrez une adresse IP à whitelister (ou appuyez sur Ctrl+C pour quitter) : ");
				string ipAddress = Console.ReadLine();

				if (string.IsNullOrEmpty(ipAddress))
				{
					Console.WriteLine("Adresse IP non valide.");
					continue;
				}

				// Assurez-vous que l'adresse IP est au bon format avant de l'ajouter à la liste blanche
				if (IPAddress.TryParse(ipAddress, out _))
				{
					// Vérifiez si l'adresse IP est déjà dans la liste blanche
					if (!IsIPWhitelisted(connection, ipAddress))
					{
						Console.WriteLine("Raison du whitelisting:");
						string raison = Console.ReadLine();
						// Whiteliste l'adresse IP
						WhitelistIP(connection, ipAddress, raison);
						Console.WriteLine($"IP {ipAddress} a été whitelistée.");

						// Vérifiez d'abord si l'adresse IP est dans la liste noire et retirez-la le cas échéant
						if (IsIPBlacklisted(connection, ipAddress))
						{
							RemoveFromBlacklist(connection, ipAddress);
							Console.WriteLine($"IP {ipAddress} a été retirée de la liste noire.");
						}
					}
					else
					{
						Console.WriteLine($"IP {ipAddress} est déjà dans la liste blanche.");
					}



				}
				else
				{
					Console.WriteLine("Adresse IP non valide.");
				}
			}
		}
	}

	static void WhitelistIP(SQLiteConnection connection, string ip, string raison)
	{
		string insertQuery = "INSERT INTO whitelist (ip, raison) VALUES (@ip,@raison)";
		using (SQLiteCommand command = new(insertQuery, connection))
		{
			command.Parameters.AddWithValue("@ip", ip);
			command.Parameters.AddWithValue("@raison", raison);
			command.ExecuteNonQuery();
		}
	}

	static bool IsIPWhitelisted(SQLiteConnection connection, string ip)
	{
		string query = "SELECT COUNT(*) FROM whitelist WHERE ip = @ip";
		using (SQLiteCommand command = new(query, connection))
		{
			command.Parameters.AddWithValue("@ip", ip);
			long count = (long)command.ExecuteScalar();
			return count > 0;
		}
	}

	static void RemoveFromBlacklist(SQLiteConnection connection, string ip)
	{
		string deleteQuery = "DELETE FROM blacklist WHERE ip = @ip";
		using (SQLiteCommand command = new(deleteQuery, connection))
		{
			command.Parameters.AddWithValue("@ip", ip);
			command.ExecuteNonQuery();
		}
	}

	static bool IsIPBlacklisted(SQLiteConnection connection, string ip)
	{
		string query = "SELECT COUNT(*) FROM blacklist WHERE ip = @ip";
		using (SQLiteCommand command = new(query, connection))
		{
			command.Parameters.AddWithValue("@ip", ip);
			long count = (long)command.ExecuteScalar();
			return count > 0;
		}
	}
}
