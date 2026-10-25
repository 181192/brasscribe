using System.Xml;
using System.Xml.Linq;

namespace Brasscribe.Play.Core.Export;

/// <summary>Single-part MusicXML from a partwise score (the "parts" export), without an engine round trip.</summary>
public static class MusicXmlParts
{
    public static IReadOnlyList<(string Id, string Name)> List(string musicXml)
    {
        var doc = Load(musicXml);
        return doc.Root!.Element("part-list")?.Elements("score-part")
            .Select(p => ((string)p.Attribute("id")!, (string?)p.Element("part-name") ?? "Part")).ToList() ?? [];
    }

    public static string Extract(string musicXml, string partId)
    {
        var doc = Load(musicXml);
        var root = doc.Root!;
        var partList = root.Element("part-list") ?? throw new FormatException("No part-list");
        if (!partList.Elements("score-part").Any(p => (string?)p.Attribute("id") == partId))
            throw new ArgumentException($"No part {partId}", nameof(partId));

        foreach (var sp in partList.Elements("score-part").Where(p => (string?)p.Attribute("id") != partId).ToList()) sp.Remove();
        foreach (var g in partList.Elements("part-group").ToList()) g.Remove();
        foreach (var p in root.Elements("part").Where(p => (string?)p.Attribute("id") != partId).ToList()) p.Remove();

        var name = (string?)partList.Element("score-part")?.Element("part-name");
        if (name is not null && root.Element("movement-title") is { } mt && !mt.Value.EndsWith(name, StringComparison.Ordinal))
            mt.Value = $"{mt.Value} – {name}";

        using var sw = new Utf8StringWriter();
        doc.Save(sw);
        return sw.ToString();
    }

    private static XDocument Load(string xml)
    {
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore, XmlResolver = null };
        using var reader = XmlReader.Create(new StringReader(xml), settings);
        var doc = XDocument.Load(reader, LoadOptions.PreserveWhitespace);
        if (doc.Root?.Name.LocalName != "score-partwise") throw new FormatException("Only score-partwise MusicXML is supported");
        return doc;
    }

    private sealed class Utf8StringWriter : StringWriter
    {
        public override System.Text.Encoding Encoding => System.Text.Encoding.UTF8;
    }
}
