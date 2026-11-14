namespace Kalli.Scribe.Capture;

public enum MediaKind { Unsupported, Audio, Video, Score, Page }

/// <summary>What the Import button accepts. Links are never downloaded (platform terms).</summary>
public static class MediaTypes
{
    // Windows reads these with Media Foundation. AIFF it cannot read at all, so it is not offered.
    public static readonly string[] AudioExtensions = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".wma", ".ogg"];
    public static readonly string[] VideoExtensions = [".mp4", ".m4v", ".mov", ".wmv", ".avi", ".mkv", ".webm"];

    /// <summary>Formats Windows reads only with a codec from the Microsoft Store (Web Media Extensions), which not every PC has.</summary>
    public static readonly string[] NeedCodecExtensions = [".ogg", ".webm", ".mkv"];

    public static bool NeedsCodec(string path) => NeedCodecExtensions.Contains(Path.GetExtension(path).ToLowerInvariant());
    public static readonly string[] ScoreExtensions = [".musicxml", ".mxl", ".xml"];

    /// <summary>A picture or PDF of printed music: the computer reads it as a page (engine: pages.py).</summary>
    public static readonly string[] PageExtensions = [".png", ".jpg", ".jpeg", ".webp", ".pdf"];

    public static IEnumerable<string> All => AudioExtensions.Concat(VideoExtensions).Concat(ScoreExtensions);

    public static MediaKind Classify(string path)
    {
        if (Uri.TryCreate(path, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https") return MediaKind.Unsupported;
        string ext = Path.GetExtension(path).ToLowerInvariant();
        if (AudioExtensions.Contains(ext)) return MediaKind.Audio;
        if (VideoExtensions.Contains(ext)) return MediaKind.Video;
        if (ScoreExtensions.Contains(ext)) return MediaKind.Score;
        if (PageExtensions.Contains(ext)) return MediaKind.Page;
        return MediaKind.Unsupported;
    }

    public static bool IsLink(string text) =>
        Uri.TryCreate(text.Trim(), UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https";
}
