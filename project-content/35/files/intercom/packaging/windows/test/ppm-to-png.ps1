# Converts Intercom's screenshots (.ppm) to .png, to look at them.
#   powershell -File ppm-to-png.ps1 -Folder $env:TEMP\intercom-shots
# Use Windows PowerShell ("powershell", built in), not PowerShell 7 ("pwsh"):
# newer .NET versions need more references for System.Drawing.
param([Parameter(Mandatory = $true)][string]$Folder)
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
public static class Ppm {
    // P6 format: "P6 <width> <height> 255", one whitespace, then RGB bytes.
    public static void ToPng(string source, string target) {
        byte[] d = File.ReadAllBytes(source);
        int pos = 0;
        string[] fields = new string[4];
        for (int i = 0; i < 4; i++) {
            while (char.IsWhiteSpace((char)d[pos])) pos++;
            int s = pos;
            while (!char.IsWhiteSpace((char)d[pos])) pos++;
            fields[i] = Encoding.ASCII.GetString(d, s, pos - s);
        }
        pos++;
        int w = int.Parse(fields[1]), h = int.Parse(fields[2]);
        using (Bitmap bmp = new Bitmap(w, h, PixelFormat.Format24bppRgb)) {
            BitmapData data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.WriteOnly, bmp.PixelFormat);
            byte[] row = new byte[data.Stride];
            for (int y = 0; y < h; y++) {
                for (int x = 0; x < w; x++) {
                    int p = pos + (y * w + x) * 3;
                    row[x * 3] = d[p + 2];      // Windows bitmaps are BGR
                    row[x * 3 + 1] = d[p + 1];
                    row[x * 3 + 2] = d[p];
                }
                Marshal.Copy(row, 0, data.Scan0 + y * data.Stride, data.Stride);
            }
            bmp.UnlockBits(data);
            bmp.Save(target, ImageFormat.Png);
        }
    }
}
"@
Get-ChildItem -Path $Folder -Filter *.ppm | ForEach-Object {
    $png = [System.IO.Path]::ChangeExtension($_.FullName, '.png')
    [Ppm]::ToPng($_.FullName, $png)
    Write-Host "Wrote $png"
}
