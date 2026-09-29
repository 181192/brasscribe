using System.Xml;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// The kit a percussion part asks for: the 0-based &lt;midi-program&gt; of its first
/// &lt;midi-instrument&gt;, per &lt;score-part&gt; in part-list order (the order alphaTab makes its
/// tracks in). alphaTab 1.8.4 reads that program but resets every percussion track to program 0 when
/// the score finishes loading, so the band map would never see the pop kit (program 1) without this.
/// </summary>
public static class PercussionKit
{
    /// <summary>Per score-part index, its first midi-program (0-based), or null when it has none.
    /// Empty when the bytes are not plain MusicXML (a compressed .mxl, say): every kit is then the band kit.</summary>
    public static IReadOnlyList<int?> Programs(byte[] musicXml)
    {
        var programs = new List<int?>();
        try
        {
            using var stream = new MemoryStream(musicXml);
            using var reader = XmlReader.Create(stream, new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore, XmlResolver = null });
            bool inPart = false, inInstrument = false;
            while (reader.Read())
            {
                if (reader.NodeType == XmlNodeType.EndElement)
                {
                    if (reader.LocalName == "score-part") inPart = false;
                    else if (reader.LocalName == "midi-instrument") inInstrument = false;
                    else if (reader.LocalName == "part-list") break;
                    continue;
                }
                if (reader.NodeType != XmlNodeType.Element) continue;
                switch (reader.LocalName)
                {
                    case "score-part":
                        programs.Add(null);
                        inPart = !reader.IsEmptyElement;
                        break;
                    case "midi-instrument":
                        inInstrument = inPart && !reader.IsEmptyElement;
                        break;
                    case "midi-program" when inInstrument && programs[^1] is null:
                        if (int.TryParse(reader.ReadElementContentAsString().Trim(), out int p)) programs[^1] = p - 1;
                        break;
                }
            }
        }
        catch (XmlException)
        {
            return [];
        }
        return programs;
    }
}
