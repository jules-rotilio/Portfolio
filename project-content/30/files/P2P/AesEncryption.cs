using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

public static class AesEncryption
{
    public static byte[] Encrypt(string plainText, string key, string iv)
    {
        byte[] keyBytes = Convert.FromBase64String(key);
        byte[] ivBytes = Convert.FromBase64String(iv);

        if (keyBytes.Length != 16 && keyBytes.Length != 24 && keyBytes.Length != 32)
        {
            throw new ArgumentException("Key must be 16, 24, or 32 bytes long.");
        }

        if (ivBytes.Length != 16)
        {
            throw new ArgumentException("IV must be 16 bytes long.");
        }

        using (Aes aesAlg = Aes.Create())
        {
            aesAlg.Key = keyBytes;
            aesAlg.IV = ivBytes;

            ICryptoTransform encryptor = aesAlg.CreateEncryptor(aesAlg.Key, aesAlg.IV);

            using (MemoryStream msEncrypt = new MemoryStream())
            {
                using (CryptoStream csEncrypt = new CryptoStream(msEncrypt, encryptor, CryptoStreamMode.Write))
                {
                    using (StreamWriter swEncrypt = new StreamWriter(csEncrypt))
                    {
                        swEncrypt.Write(plainText);
                    }
                    return msEncrypt.ToArray();
                }
            }
        }
    }

    public static string Decrypt(byte[] cipherText, string key, string iv)
    {
        byte[] keyBytes = Convert.FromBase64String(key);
        byte[] ivBytes = Convert.FromBase64String(iv);

        if (keyBytes.Length != 16 && keyBytes.Length != 24 && keyBytes.Length != 32)
        {
            throw new ArgumentException("Key must be 16, 24, or 32 bytes long.");
        }

        if (ivBytes.Length != 16)
        {
            throw new ArgumentException("IV must be 16 bytes long.");
        }

        using (Aes aesAlg = Aes.Create())
        {
            aesAlg.Key = keyBytes;
            aesAlg.IV = ivBytes;

            ICryptoTransform decryptor = aesAlg.CreateDecryptor(aesAlg.Key, aesAlg.IV);

            using (MemoryStream msDecrypt = new MemoryStream(cipherText))
            {
                using (CryptoStream csDecrypt = new CryptoStream(msDecrypt, decryptor, CryptoStreamMode.Read))
                {
                    using (StreamReader srDecrypt = new StreamReader(csDecrypt))
                    {
                        return srDecrypt.ReadToEnd();
                    }
                }
            }
        }
    }
}
