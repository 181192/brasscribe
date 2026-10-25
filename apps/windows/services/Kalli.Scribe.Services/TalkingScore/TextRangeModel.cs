namespace Brasscribe.Play.Core.TalkingScore;

/// <summary>UI Automation text units, in the order UIA defines them.</summary>
public enum TextUnitKind { Character = 0, Format = 1, Word = 2, Line = 3, Paragraph = 4, Page = 5, Document = 6 }

/// <summary>
/// A [Start, End) range over the talking-score text with the unit movement rules of the UIA
/// TextPattern (ITextRangeProvider): degenerate ranges, ExpandToEnclosingUnit, Move and
/// MoveEndpointByUnit. The WinUI provider wraps this; each event is one line.
/// </summary>
public sealed class TextRangeModel
{
    public TextRangeModel(string text, int start, int end)
    {
        Text = text;
        Start = Math.Clamp(start, 0, text.Length);
        End = Math.Clamp(end, Start, text.Length);
    }

    public string Text { get; }
    public int Start { get; private set; }
    public int End { get; private set; }
    public bool IsDegenerate => Start == End;

    public TextRangeModel Clone() => new(Text, Start, End);

    public string GetText(int maxLength)
    {
        string s = Text[Start..End];
        return maxLength >= 0 && s.Length > maxLength ? s[..maxLength] : s;
    }

    public void SetEndpoint(bool start, int position)
    {
        position = Math.Clamp(position, 0, Text.Length);
        if (start)
        {
            Start = position;
            if (End < Start) End = Start;
        }
        else
        {
            End = position;
            if (Start > End) Start = End;
        }
    }

    public void ExpandToEnclosingUnit(TextUnitKind unit)
    {
        int s = UnitStart(Start, unit);
        // UIA: expand when smaller than the unit, shorten when longer, anchored at the start.
        Start = s;
        End = UnitEnd(s, unit);
    }

    /// <summary>Moves the whole range by count units and makes it that unit; returns units moved.</summary>
    public int Move(TextUnitKind unit, int count)
    {
        if (count == 0) return 0;
        int pos = UnitStart(Start, unit);
        int moved = 0;
        while (moved < Math.Abs(count))
        {
            int next = count > 0 ? UnitEnd(pos, unit) : pos == 0 ? -1 : UnitStart(pos - 1, unit);
            if (next < 0 || (count > 0 && next >= Text.Length)) break;
            pos = next;
            moved++;
        }
        bool degenerate = IsDegenerate;
        Start = pos;
        End = degenerate ? pos : UnitEnd(pos, unit);
        return count > 0 ? moved : -moved;
    }

    public int MoveEndpointByUnit(bool start, TextUnitKind unit, int count)
    {
        int pos = start ? Start : End;
        int moved = 0;
        while (moved < Math.Abs(count))
        {
            int next = count > 0
                ? (pos >= Text.Length ? -1 : UnitEnd(UnitStart(pos, unit), unit))
                : (pos <= 0 ? -1 : UnitStart(pos - 1, unit));
            if (next < 0 || next == pos) break;
            pos = next;
            moved++;
        }
        SetEndpoint(start, pos);
        return count > 0 ? moved : -moved;
    }

    /// <summary>Index of the first occurrence of text inside the range, or -1.</summary>
    public int Find(string needle, bool backward, bool ignoreCase)
    {
        var cmp = ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        string hay = Text[Start..End];
        int i = backward ? hay.LastIndexOf(needle, cmp) : hay.IndexOf(needle, cmp);
        return i < 0 ? -1 : Start + i;
    }

    /// <summary>Line index (0-based) of a position.</summary>
    public int LineOf(int position)
    {
        int line = 0;
        for (int i = 0; i < Math.Min(position, Text.Length); i++) if (Text[i] == '\n') line++;
        return line;
    }

    public static (int Start, int End) LineSpan(string text, int line)
    {
        int s = 0;
        for (int l = 0; l < line; l++)
        {
            int nl = text.IndexOf('\n', s);
            if (nl < 0) return (text.Length, text.Length);
            s = nl + 1;
        }
        int e = text.IndexOf('\n', s);
        return (s, e < 0 ? text.Length : e + 1);
    }

    private int UnitStart(int pos, TextUnitKind unit)
    {
        pos = Math.Clamp(pos, 0, Text.Length);
        switch (unit)
        {
            case TextUnitKind.Character or TextUnitKind.Format:
                return Math.Min(pos, Math.Max(0, Text.Length - 1));
            case TextUnitKind.Word:
                while (pos > 0 && !char.IsWhiteSpace(Text[pos - 1])) pos--;
                return pos;
            case TextUnitKind.Line or TextUnitKind.Paragraph:
                while (pos > 0 && Text[pos - 1] != '\n') pos--;
                return pos;
            default:
                return 0;
        }
    }

    private int UnitEnd(int start, TextUnitKind unit)
    {
        switch (unit)
        {
            case TextUnitKind.Character or TextUnitKind.Format:
                return Math.Min(start + 1, Text.Length);
            case TextUnitKind.Word:
            {
                int p = start;
                while (p < Text.Length && !char.IsWhiteSpace(Text[p])) p++;
                while (p < Text.Length && char.IsWhiteSpace(Text[p])) p++;
                return p;
            }
            case TextUnitKind.Line or TextUnitKind.Paragraph:
            {
                int nl = Text.IndexOf('\n', start);
                return nl < 0 ? Text.Length : nl + 1;
            }
            default:
                return Text.Length;
        }
    }
}
