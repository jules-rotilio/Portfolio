using MineStatLib;

var serverAddress = "203.0.113.10";
ushort port = 25573;

var mineStat = new MineStat(serverAddress, port);

if (mineStat.ServerUp)
{
    Console.WriteLine($"Nombre de joueurs : {mineStat.CurrentPlayers}");
    Console.WriteLine("Pseudos des joueurs :");

    if (mineStat.PlayerList != null)
    {
        foreach (var player in mineStat.PlayerList)
        {
            Console.WriteLine(player);
        }
    }
    else
    {
        Console.WriteLine("Aucun joueur connecté.");
    }
    Console.WriteLine($"Motd : {mineStat.Motd}");
    Console.WriteLine($"Version du serveur : {mineStat.Version}");
}
else
{
    Console.WriteLine("Impossible de se connecter au serveur.");
}
