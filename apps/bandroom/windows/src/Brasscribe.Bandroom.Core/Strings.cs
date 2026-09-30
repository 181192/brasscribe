using System.Globalization;
using System.Xml.Linq;

namespace Brasscribe.Bandroom.Core;

/// <summary>Localized copy (design/server-app.md §10). Keys are the deck's keys with "_" for "." and "-".</summary>
public interface IStrings
{
    string this[string key] { get; }
    /// <summary>"nb" or "en".</summary>
    string Language { get; }
    CultureInfo Culture { get; }
}

public static class StringsExtensions
{
    public static string Format(this IStrings s, string key, params object?[] args) =>
        string.Format(s.Culture, s[key], args);
}

/// <summary>Reads a .resw table: the app's own files, used by tests and anywhere without ResourceLoader.</summary>
public sealed class ReswStrings : IStrings
{
    private readonly Dictionary<string, string> _values;

    public ReswStrings(string reswPath, string language)
    {
        _values = XDocument.Load(reswPath).Root!.Elements("data")
            .ToDictionary(d => (string)d.Attribute("name")!, d => (string?)d.Element("value") ?? "");
        Language = language;
        Culture = CultureInfo.GetCultureInfo(language == "nb" ? "nb-NO" : "en-GB");
    }

    public IReadOnlyDictionary<string, string> All => _values;
    public string this[string key] => _values.TryGetValue(key, out var v) ? v : throw new KeyNotFoundException(key);
    public string Language { get; }
    public CultureInfo Culture { get; }
}

/// <summary>Screen readers read the six-digit code digit by digit, the QR as what it holds.</summary>
public static class CodeText
{
    /// <summary>"482913" shown as "482 913".</summary>
    public static string Display(string code)
    {
        var digits = new string(code.Where(char.IsDigit).ToArray());
        return digits.Length == 6 ? digits[..3] + " " + digits[3..] : digits;
    }

    /// <summary>"Code: 4 8 2, 9 1 3".</summary>
    public static string Spoken(IStrings s, string code)
    {
        var d = code.Where(char.IsDigit).Select(c => (object?)c.ToString()).ToArray();
        return d.Length == 6 ? s.Format("Pair_Code_A11y", d) : code;
    }

    /// <summary>"192.0.2.20" read as "192 dot 0 dot 2 dot 20".</summary>
    public static string SpokenAddress(IStrings s, string ip) => ip.Replace(".", " " + s["Dot"] + " ", StringComparison.Ordinal);
}
