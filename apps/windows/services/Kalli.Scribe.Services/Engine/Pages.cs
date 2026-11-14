namespace Kalli.Scribe.Engine;

/// <summary>
/// Pages of printed music the computer reads instead of a recording: pictures and PDFs, in order (engine: pages.py,
/// sheet.py). What a file is, is read from its first bytes, as the engine reads it.
/// </summary>
public static class Pages
{
    /// <summary>The most files one job takes, and the largest one may be (engine: pages.py).</summary>
    public const int MaxPages = 40;
    public const long MaxPageBytes = 50L * 1024 * 1024;

    /// <summary>The file types the file dialog offers for pages.</summary>
    public static readonly string[] Extensions = [".png", ".jpg", ".jpeg", ".webp", ".pdf"];

    /// <summary>What the engine reads as it is, by the file's first bytes: png, jpeg, webp or pdf; null for anything else.</summary>
    public static string? FormatOf(ReadOnlySpan<byte> head)
    {
        static bool At(ReadOnlySpan<byte> h, int i, ReadOnlySpan<byte> bytes) => h.Length >= i + bytes.Length && h.Slice(i, bytes.Length).SequenceEqual(bytes);
        if (At(head, 0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) return "png";
        if (At(head, 0, [0xFF, 0xD8, 0xFF])) return "jpeg";
        if (At(head, 0, "RIFF"u8) && At(head, 8, "WEBP"u8)) return "webp";
        if (At(head, 0, "%PDF-"u8)) return "pdf";
        return null;
    }

    /// <summary>Why a file cannot be one of the pages, or null when it can: not a picture or PDF the engine reads, or too large.</summary>
    public static PageRefusal? Check(string path)
    {
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists) return PageRefusal.NotAPage;
            if (info.Length > MaxPageBytes) return PageRefusal.TooLarge;
            Span<byte> head = stackalloc byte[12];
            using var file = File.OpenRead(path);
            int n = file.ReadAtLeast(head, head.Length, throwOnEndOfStream: false);
            return FormatOf(head[..n]) is null ? PageRefusal.NotAPage : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return PageRefusal.NotAPage;
        }
    }

    /// <summary>The codes the computer refuses pages with before a job is made ({"code", "detail"}).</summary>
    public const string NotAPage = "not_a_page";
    public const string WrongInput = "wrong_input";
    public const string PageTooLarge = "page_too_large";
    public const string TooManyPages = "too_many_pages";
    public const string ReaderMissing = "reader_missing";

    /// <summary>The fixed words a job that could not read its pages ends its error with (engine: sheet.py), by its name.</summary>
    public static readonly IReadOnlyList<(string Words, string Name)> Failures =
    [
        ("no notes were found on the page", "NoMusic"),
        ("no staff of notes was found on the page: a tab staff is not read", "OnlyTab"),
        ($"there are more than {MaxPages} pages", "TooManyPages"),
        ("a page is too large to read", "PageTooLarge"),
        ("the reader's files could not be fetched: check the network and try again", "ReaderFilesMissing"),
        ("the computer's disk is full: free some space on it and try again", "DiskFull"),
        ("the pages could not be read", "NotRead"),
    ];

    /// <summary>Which of the reader's failures a job's error is, or null for any other. The words end the error, or its first line.</summary>
    public static string? FailureOf(string? error)
    {
        if (error is null) return null;
        string whole = error.Trim();
        string first = whole.Split('\n', 2)[0].Trim();
        foreach (var (words, name) in Failures)
            if (whole.EndsWith(words, StringComparison.Ordinal) || first.EndsWith(words, StringComparison.Ordinal)) return name;
        return null;
    }
}

/// <summary>Why a file chosen as a page is left out on this PC.</summary>
public enum PageRefusal { NotAPage, TooLarge }
