using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Bridge;

/// <summary>
/// Calls the Rust core through its C ABI (library brasscribe_ffi, core/bindings/c/brasscribe.h).
/// Every call takes UTF-8 NUL-terminated strings and returns 0 ok, 1 invalid input, 2 failed,
/// 3 null argument or 4 panic; strings come back through out-parameters released with bc_string_free.
/// The library is looked up next to the app, or at BRASSCRIBE_FFI_PATH; when it is missing or lacks
/// one of the functions used here, <see cref="TryCreate"/> returns null and the managed bridge is used.
/// </summary>
public sealed partial class NativeCoreBridge : ICoreBridge
{
    private const string Lib = "brasscribe_ffi";

    /// <summary>Every export this bridge calls; an older library without them is not used.</summary>
    internal static readonly string[] RequiredExports =
    [
        "bc_version", "bc_string_free", "bc_composition_normalize", "bc_arrange_musicxml", "bc_arrange_layers_band",
        "bc_humanize_json", "bc_talking_score_new", "bc_talking_score_free", "bc_talking_score_json", "bc_talking_announce_json",
    ];

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
        foreach (var export in RequiredExports)
            if (!NativeLibrary.TryGetExport(_handle, export, out _)) return null;
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
        TalkingScoreJson.Parse(TalkingScoreDocumentJson(musicXml, composition is null ? null : CompositionJson.Serialize(composition)));

    /// <summary>The talking-score document as the core writes it (spec §6 JSON).</summary>
    public string TalkingScoreDocumentJson(string musicXml, string? compositionJson)
    {
        Check(bc_talking_score_new(musicXml, compositionJson, out var ts, out var err), err);
        try
        {
            Check(bc_talking_score_json(ts, out var json, out err), err);
            return Take(json);
        }
        finally
        {
            bc_talking_score_free(ts);
        }
    }

    public string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context, TalkingScoreSettings settings, bool byBar = false)
    {
        var request = TalkingScoreJson.AnnounceRequest(part, bar, ev, context, settings, byBar);
        Check(bc_talking_announce_json(request, out var json, out var err), err);
        return Take(json);
    }

    public string? ArrangeMusicXml(Composition composition, string arranger = "auto")
    {
        Check(bc_arrange_musicxml(CompositionJson.Serialize(composition), arranger, out var xml, out var err), err);
        return Take(xml);
    }

    public BandArrangement? ArrangeLayersBand(LayerInputs inputs, string title, ArrangementOptions options)
    {
        if (inputs.Midi.Length != 6 || inputs.Wav.Length != 4) throw new ArgumentException("six MIDI layers and four stems expected", nameof(inputs));
        var pins = new List<GCHandle>();
        try
        {
            nint Pin(byte[]? bytes)
            {
                if (bytes is null) return 0;
                var h = GCHandle.Alloc(bytes, GCHandleType.Pinned);
                pins.Add(h);
                return h.AddrOfPinnedObject();
            }
            var midi = inputs.Midi.Select(Pin).ToArray();
            var midiLen = inputs.Midi.Select(b => (nuint)b.Length).ToArray();
            var wav = inputs.Wav.Select(Pin).ToArray();
            var wavLen = inputs.Wav.Select(b => (nuint)(b?.Length ?? 0)).ToArray();
            Check(bc_arrange_layers_band(midi, midiLen, wav, wavLen, inputs.Beats, title, LayersOptions(inputs.Contour, options), out var json, out var err), err);
            var o = JsonNode.Parse(Take(json))!.AsObject();
            var parts = o["parts"]?.AsArray().Select(p => (p!["file_name"]!.GetValue<string>(), p["musicxml"]!.GetValue<string>())).ToList() ?? [];
            return new BandArrangement(o["composition"]!.GetValue<string>(), o["musicxml"]!.GetValue<string>(), parts,
                o["separation_check"] is JsonValue sc && sc.TryGetValue(out string? check) ? check : null);
        }
        finally
        {
            foreach (var h in pins) h.Free();
        }
    }

    /// <summary>The options JSON of bc_arrange_layers_band. The core calls the full lineup "band".</summary>
    internal static string LayersOptions(SoloContour? contour, ArrangementOptions options)
    {
        static JsonArray Floats(IEnumerable<double> v, double nanAs) => new(v.Select(x => (JsonNode?)JsonValue.Create(double.IsFinite(x) ? x : nanAs)).ToArray());
        var o = new JsonObject
        {
            ["lineup"] = options.Lineup == "minimal" ? "minimal" : "band",
            ["difficulty"] = options.Difficulty,
        };
        if (options.Key is { } key) o["key"] = key;
        if (options.Transpose is { } t) o["transpose"] = t;
        if (contour is not null)
            o["solo_contour"] = new JsonObject
            {
                ["times"] = Floats(contour.Times, 0),
                // Unvoiced frames: the core reads any pitch at or below 0 Hz as no pitch.
                ["pitch_hz"] = Floats(contour.PitchHz, 0),
                ["loudness_db"] = Floats(contour.LoudnessDb, -140),
            };
        return o.ToJsonString();
    }

    public HumanizedPart? Humanize(IReadOnlyList<HumanizeNote> notes, string part, int player, string? compositionJson)
    {
        var request = new JsonObject
        {
            ["notes"] = new JsonArray(notes.Select(n => (JsonNode?)new JsonObject
            {
                ["tick"] = n.Tick, ["dur_tick"] = n.DurTick, ["start_s"] = n.StartS, ["end_s"] = n.EndS,
                ["pitch"] = n.Pitch, ["velocity"] = n.Velocity,
            }).ToArray()),
            ["part"] = part,
            ["player"] = player,
            ["seed"] = "brasscribe",
            ["timing"] = "score",
        };
        if (compositionJson is not null) request["composition"] = JsonNode.Parse(compositionJson);
        Check(bc_humanize_json(request.ToJsonString(), out var json, out var err), err);
        using var doc = JsonDocument.Parse(Take(json));
        var root = doc.RootElement;
        var played = root.GetProperty("notes").EnumerateArray().Select(n => new PlayedNote(
            n.GetProperty("start").GetDouble(), n.GetProperty("end").GetDouble(), n.GetProperty("pitch").GetInt32(),
            (int)n.GetProperty("velocity").GetDouble(), n.GetProperty("staccato").GetBoolean(), n.GetProperty("from_composition").GetBoolean())).ToList();
        return new HumanizedPart(played, root.TryGetProperty("detune", out var d) ? d.GetDouble() : 0);
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

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_arrange_layers_band(nint[] midi, nuint[] midiLen, nint[] wav, nuint[] wavLen,
        string beatsText, string title, string options, out nint json, out nint err);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_humanize_json(string request, out nint json, out nint err);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_talking_score_new(string musicXml, string? compositionJson, out nint ts, out nint err);

    [LibraryImport(Lib)]
    private static partial void bc_talking_score_free(nint ts);

    [LibraryImport(Lib)]
    private static partial int bc_talking_score_json(nint ts, out nint json, out nint err);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int bc_talking_announce_json(string request, out nint json, out nint err);
}

public sealed class CoreBridgeException(string message, int status) : Exception(message)
{
    public int Status { get; } = status;
}
