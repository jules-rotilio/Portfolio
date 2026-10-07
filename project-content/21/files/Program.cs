using System;
using System.Collections.Generic;

class Program
{
    static void Main()
    {
        List<byte[]> memoryHog = new List<byte[]>();

        while (true)
        {
            memoryHog.Add(new byte[1024 * 1024]); // Allocate 1 MB of memory in each iteration
            Console.WriteLine("Allocated memory");
        }
    }
}
