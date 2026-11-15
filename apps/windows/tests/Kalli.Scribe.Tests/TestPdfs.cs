using Kalli.Scribe.Engine;

namespace Kalli.Scribe.Tests;

/// <summary>
/// A PDF reader for the tests, which run without the system's (Windows.Data.Pdf): it reads the tests' invented PDFs (a
/// page tree's "/Count", or pages named one by one) and nothing else. A file with "/Encrypt" is locked; one cut short
/// (no "%%EOF") or with no page is damaged.
/// </summary>
internal static class TestPdfs
{
    public static Task<PdfRead> ReadAsync(string path)
    {
        string text = System.Text.Encoding.Latin1.GetString(File.ReadAllBytes(path));
        if (text.Contains("/Encrypt")) return Task.FromResult(PdfRead.Locked);
        int count = System.Text.RegularExpressions.Regex.Matches(text, @"/Count (\d+)").Select(m => int.Parse(m.Groups[1].Value)).DefaultIfEmpty(0).Max();
        if (count == 0) count = System.Text.RegularExpressions.Regex.Matches(text, @"/Type ?/Page[ >]").Count;
        return Task.FromResult(!text.Contains("%%EOF") || count == 0 ? PdfRead.Damaged : new PdfRead(count));
    }
}
