using System;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Configuration;

namespace Cascade
{
    /// <summary>
    /// Représente la connexion à la base de données SQLite
    /// </summary>
    public class Connection : SqliteConnection
    {
        /// <summary>
        /// instance de la connexion à la database
        /// </summary>
        private static Connection? Instance { get; set; } = null;

        /// <summary>
        /// Retourne l'instance du singleton de la connexion à la database
        /// </summary>
        /// <returns>Le singleton de la classe Connection</returns>
        public static Connection GetInstance(IConfiguration configuration)
        {
            if (Instance == null)
            {
                Instance = new Connection(configuration["db_source"]);
            }
            else if (Instance.State == System.Data.ConnectionState.Closed)
            {
                Instance.Open();
            }
            return Instance;
        }

        /// <summary>
        /// Connexion à la base de données SQLite
        /// </summary>
        /// <param name="databasePath">Chemin vers le fichier contenant la DataBase</param>
        public Connection(string? databasePath) : base($"Data Source={databasePath}")
        {
            Console.WriteLine(ConnectionString);
            Open();
        }
        public bool NotExists(string? guid, long datetime)
        {
            string commandText = @$"
            SELECT COUNT(*) FROM RssItem WHERE GUID = '{guid}' AND Pub_Date = {datetime};
        ";
            Console.WriteLine(commandText);
            using SqliteCommand command = new(commandText, this);
            int rowCount = Convert.ToInt32(command.ExecuteScalar());
            return rowCount == 0;
        }
        public void Create_Item_Row(ulong cid, string? guid, long pubdate)
        {
            using var command = CreateCommand();
            command.CommandText = @"
            Insert into RssItem 
                (Channel_ID, GUID, Pub_Date) 
            values
                ($channelid,$guid,$pubdate)
        ";
            command.Parameters.AddWithValue("$guid", guid);
            command.Parameters.AddWithValue("$channelid", cid);
            command.Parameters.AddWithValue("$pubdate", pubdate);
            command.ExecuteNonQuery();
        }

        public void Create_Channel_Row(ulong cid, string url, uint color)
        {
            using var command = CreateCommand();
            command.CommandText = @"
            Insert into RssChannel 
                (Channel_ID, Url_Rss, Color, Last_ID) 
            values
                ($channelid,$url,$color,0)
        ";
            command.Parameters.AddWithValue("$url", url);
            command.Parameters.AddWithValue("$channelid", cid);
            command.Parameters.AddWithValue("$color", color);
            command.ExecuteNonQuery();
        }

        public void Edit_Channel_Row(ulong cid, long date)
        {
            using var command = CreateCommand();
            command.CommandText = @"
            UPDATE RssChannel SET LAST_ID = $lastdate WHERE Channel_ID = $channelid
        ";
            command.Parameters.AddWithValue("$lastdate", date);
            command.Parameters.AddWithValue("$channelid", cid);
            command.ExecuteNonQuery();
        }



        /// <summary>
        /// Initialise des tables dans la DataBase.
        /// <para>Crée des tables si la DB n'est pas encore initialisée.</para>
        /// <para>Ferme le programme si erreur.</para>
        /// </summary>
        public void InitDB()
        {
            var command = CreateCommand();
            command.CommandText = @"
CREATE TABLE IF NOT EXISTS RssChannel (
    Channel_ID INTEGER PRIMARY KEY,
    Url_Rss TEXT,
    Color TEXT,
    Last_ID TEXT
);

CREATE TABLE IF NOT EXISTS RssItem (
    Pub_Date TEXT,
    GUID TEXT,
    Channel_ID INTEGER,
    FOREIGN KEY(Channel_ID) REFERENCES RssChannel(Channel_ID),
    PRIMARY KEY (Pub_Date, GUID),
    UNIQUE (Pub_Date, GUID)
);
DROP TABLE IF EXISTS serveur;
            ";
            try
            {
                command.ExecuteNonQuery();
                Console.WriteLine("Init database done");
            }
            catch (SqliteException e)
            {
                Console.WriteLine(e);
                Console.WriteLine("Error : Cannot init database.");
                Console.WriteLine("Exiting now.");
                Environment.Exit(1);
            }
        }
    }

}
