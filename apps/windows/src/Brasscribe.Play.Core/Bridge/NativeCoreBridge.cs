using System.Runtime.InteropServices;
using System.Text.Json;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Bridge;

/// <summary>
/// Calls the Rust core through its C ABI (library brasscribe_ffi). Every call takes UTF-8
/// NUL-terminated strings, returns 0 on success, and hands back strings through out-parameters
/// that are released with bc_string_free. The ABI is being built alongside this app; until the
/// library ships with the app, <see cref="TryCreate"/> returns null and the managed bridge is used.
/// Talking-score functions are not in the Rust core, so they stay managed here.
/// </summary>
public sealed partial class NativeCoreBridge : ICoreBridge
{
    private const string Lib = "brasscribe_ffi";
    private readonly ManagedCoreBridge _managed = new();

    private NativeCoreBridge(string version) => Version = version;

    public string Version { get; }
    public bool IsNative => true;

    /// <summary>Loads the native core if present next to the app; null when it is missing or incompatible.</summary>
    public static NativeCoreBridge? TryCreate()
    {
        if (!NativeLibrary.TryLoad(Lib, typeof(NativeCoreBridge).Assembly, null, out var handle)) return null;
        try
        {
            if (!NativeLibrary.TryGetExport(handle, "bc_version", out _)) return null;
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
        Check(bc_composition_validate(json, out var normalised, out var err), err);
        return CompositionJson.Parse(Take(normalised));
    }

    public TalkingScoreDocument BuildTalkingScore(string musicXml, Composition? composition) =>
        _managed.BuildTalkingScore(musicXml, composition);

    public string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context, TalkingScoreSettings settings, bool byBar = false) =>
        _managed.Announce(part, bar, ev, context, settings, byBar);

    public string? ArrangeMusicXml(Composition composition, string arranger = "auto")
    {
        string options = JsonSerializer.Serialize(new Dictionary<string, string> { ["arranger"] = arranger },
            BridgeJsonContext.Default.DictionaryStringString);
        Check(bc_arrange_musicxml(CompositionJson.Serialize(composition), options, out var xml, out var err), err);
        return Take(xml);
    }

    private static void Check(int status, nint err)
    {
        if (status == 0)
        {
            if (err != 0) bc_string_free(err);
            return;
        }
        string message = err != 0 ? Take(err) : $"core error {status}";
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
    private static partial int bc_composition_validate(string json, out nint normalised, out nint err);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_arrange_musicxml(string compositionJson, string optionsJson, out nint xml, out nint err);
}

public sealed class CoreBridgeException(string message, int status) : Exception(message)
{
    public int Status { get; } = status;
}

[System.Text.Json.Serialization.JsonSerializable(typeof(Dictionary<string, string>))]
internal sealed partial class BridgeJsonContext : System.Text.Json.Serialization.JsonSerializerContext;
