using System.Runtime.InteropServices;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Bridge;

/// <summary>
/// Calls the Rust core through its C ABI (library brasscribe_ffi, core/bindings/c/brasscribe.h).
/// Every call takes UTF-8 NUL-terminated strings and returns 0 ok, 1 invalid input, 2 failed,
/// /// 3 null argument or 4 panic; strings come back through out-parameters released with bc_string_free.
/// The library is looked up next to the app, or at BRASSCRIBE_FFI_PATH; when it is missing
/// <see cref="TryCreate"/> returns null and the managed bridge is used.
/// Talking-score functions are not in the Rust core, so they stay managed here.
/// </summary>
public sealed partial class NativeCoreBridge : ICoreBridge
{
    private const string Lib = "brasscribe_ffi";
    private readonly ManagedCoreBridge _managed = new();

    private NativeCoreBridge(string version) => Version = version;

    public string Version { get; }
    public bool IsNative => true;

    private static nint _handle;
    private static bool _resolverSet;
    private static readonly object Gate = new();

    /// <summary>Loads the native core if present; null when it is missing or incompatible.</summary>
    public static NativeCoreBridge? TryCreate(string? libraryPath = null)
    {
        libraryPath ??= Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH");
        lock (Gate)
        {
            if (_handle == 0)
            {
                bool loaded = libraryPath is { Length: > 0 }
                    ? NativeLibrary.TryLoad(libraryPath, out _handle)
                    : NativeLibrary.TryLoad(Lib, typeof(NativeCoreBridge).Assembly, null, out _handle);
                if (!loaded) return null;
            }
            if (!_resolverSet)
            {
                NativeLibrary.SetDllImportResolver(typeof(NativeCoreBridge).Assembly,
                    (name, _, _) => name == Lib ? _handle : 0);
                _resolverSet = true;
            }
        }
        if (!NativeLibrary.TryGetExport(_handle, "bc_version", out _)) return null;
        try
        {
            nint v = bc_version();
            try { return new NativeCoreBridge(Marshal.PtrToStringUTF8(v) ?? "native"); }
            finally { bc_string_free(v); }
        }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException or BadImageFormatException)
        {
            return null;
        }
    }

    public Composition ParseComposition(string json)
    {
        Check(bc_composition_normalize(json, out var normalised, out var err), err);
        return CompositionJson.Parse(Take(normalised));
    }

    public TalkingScoreDocument BuildTalkingScore(string musicXml, Composition? composition) =>
        _managed.BuildTalkingScore(musicXml, composition);

    public string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context, TalkingScoreSettings settings, bool byBar = false) =>
        _managed.Announce(part, bar, ev, context, settings, byBar);

    public string? ArrangeMusicXml(Composition composition, string arranger = "auto")
    {
        Check(bc_arrange_musicxml(CompositionJson.Serialize(composition), arranger, out var xml, out var err), err);
        return Take(xml);
    }

    private static void Check(int status, nint err)
    {
        if (status == 0)
        {
            if (err != 0) bc_string_free(err);
            return;
        }
        string kind = status switch { 1 => "invalid input", 2 => "failed", 3 => "missing argument", 4 => "internal error", _ => $"error {status}" };
        string message = err != 0 ? $"{kind}: {Take(err)}" : kind;
        throw new CoreBridgeException(message, status);
    }

    private static string Take(nint p)
    {
        try { return Marshal.PtrToStringUTF8(p) ?? ""; }
        finally { if (p != 0) bc_string_free(p); }
    }

    [LibraryImport(Lib)]
    private static partial nint bc_version();

    [LibraryImport(Lib)]
    private static partial void bc_string_free(nint s);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_composition_normalize(string json, out nint normalised, out nint err);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_arrange_musicxml(string compositionJson, string arranger, out nint xml, out nint err);
}

public sealed class CoreBridgeException(string message, int status) : Exception(message)
{
    public int Status { get; } = status;
}
