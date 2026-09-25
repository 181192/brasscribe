namespace Brasscribe.Play.Core.Capture;

public enum MediaKind { Unsupported, Audio, Video, Score }

/// <summary>What the Import button accepts. Links are never downloaded (platform terms).</summary>
public static class MediaTypes
{
    public static readonly string[] AudioExtensions = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".wma", ".ogg", ".aiff", ".aif"];
    public static readonly string[] VideoExtensions = [".mp4", ".m4v", ".mov", ".wmv", ".avi", ".mkv", ".webm"];
    public static readonly string[] ScoreExtensions = [".musicxml", ".mxl", ".xml"];

    public static IEnumerable<string> All => AudioExtensions.Concat(VideoExtensions).Concat(ScoreExtensions);

    public static MediaKind Classify(string path)
    {
        if (Uri.TryCreate(path, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https") return MediaKind.Unsupported;
        string ext = Path.GetExtension(path).ToLowerInvariant();
        if (AudioExtensions.Contains(ext)) return MediaKind.Audio;
        if (VideoExtensions.Contains(ext)) return MediaKind.Video;
        if (ScoreExtensions.Contains(ext)) return MediaKind.Score;
        return MediaKind.Unsupported;
    }

    public static bool IsLink(string text) =>
        Uri.TryCreate(text.Trim(), UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https";
}
