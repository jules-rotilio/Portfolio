using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using Portfolio.Api.Models;

namespace Portfolio.Api.Services
{
    /// <summary>
    /// Captcha par preuve de travail (sans service tiers ni cookie) : le navigateur doit retrouver le nombre
    /// tel que SHA-256(salt + nombre) == challenge. Le challenge est signé (HMAC) pour ne pas pouvoir être fabriqué,
    /// le salt contient sa date d'expiration et une solution ne sert qu'une fois.
    /// </summary>
    public class CaptchaService
    {
        public const int MaxNumber = 100_000;
        private static readonly TimeSpan Lifetime = TimeSpan.FromMinutes(10);

        // Clé propre au processus : un redémarrage invalide seulement les captchas en cours
        private readonly byte[] _key = RandomNumberGenerator.GetBytes(32);
        private readonly ConcurrentDictionary<string, long> _usedSalts = new();

        public CaptchaChallenge Create()
        {
            var expires = DateTimeOffset.UtcNow.Add(Lifetime).ToUnixTimeSeconds();
            var salt = $"{expires}.{Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(12))}";
            var challenge = Hash(salt, RandomNumberGenerator.GetInt32(MaxNumber + 1));
            return new CaptchaChallenge(salt, challenge, MaxNumber, Sign(challenge));
        }

        public bool Verify(CaptchaSolution solution)
        {
            var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var dot = solution.Salt.IndexOf('.');
            if (dot <= 0 || !long.TryParse(solution.Salt.AsSpan(0, dot), out var expires) || expires < now
                || solution.Number is < 0 or > MaxNumber)
            {
                return false;
            }

            var expected = Encoding.ASCII.GetBytes(Sign(Hash(solution.Salt, solution.Number)));
            if (!CryptographicOperations.FixedTimeEquals(expected, Encoding.ASCII.GetBytes(solution.Signature)))
            {
                return false;
            }

            foreach (var used in _usedSalts.Where(u => u.Value < now))
            {
                _usedSalts.TryRemove(used.Key, out _);
            }
            return _usedSalts.TryAdd(solution.Salt, expires);
        }

        public static string Hash(string salt, int number) =>
            Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(salt + number)));

        private string Sign(string challenge) =>
            Convert.ToHexStringLower(HMACSHA256.HashData(_key, Encoding.ASCII.GetBytes(challenge)));
    }
}
