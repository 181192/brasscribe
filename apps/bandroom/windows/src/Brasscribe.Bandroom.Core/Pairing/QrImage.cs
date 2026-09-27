using QRCoder;

namespace Brasscribe.Bandroom.Core.Pairing;

/// <summary>
/// The pairing QR: always black on a white plate with a 4-module quiet zone, in every theme, because
/// many scanners can't read inverted codes (§9, high contrast).
/// </summary>
public static class QrImage
{
    public static byte[] Png(string payload, int pixelsPerModule = 6)
    {
        using var gen = new QRCodeGenerator();
        using var data = gen.CreateQrCode(payload, QRCodeGenerator.ECCLevel.M);
        return new PngByteQRCode(data).GetGraphic(pixelsPerModule, [0, 0, 0, 255], [255, 255, 255, 255], drawQuietZones: true);
    }

    /// <summary>Modules per side including the quiet zone.</summary>
    public static int Modules(string payload)
    {
        using var gen = new QRCodeGenerator();
        using var data = gen.CreateQrCode(payload, QRCodeGenerator.ECCLevel.M);
        return data.ModuleMatrix.Count;
    }
}
