using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace Brasscribe.Core;

/// <summary>Error reported by the native core.</summary>
public sealed class BrasscribeException : Exception
{
    public BrasscribeException(int code, string message) : base(message) => Code = code;

    /// <summary>1 invalid input, 2 pipeline failure, 3 null argument, 4 internal error.</summary>
    public int Code { get; }
}

/// <summary>A spelled pitch: step "C".."B", alteration in semitones, octave (C4 = middle C).</summary>
public readonly record struct SpelledPitch(string Step, int Alter, int Octave);

/// <summary>Frame-level SwiftF0 contour of the solo stem; Confidence (per-frame voicing) feeds the notes' calibrated confidence.</summary>
public sealed record SoloContour(double[] Times, double[] PitchHz, double[] LoudnessDb, double[]? Confidence = null);

/// <summary>The six layer transcriptions (MIDI file bytes) of a recording.</summary>
public sealed record LayerMidi(byte[] SoloSwiftF0, byte[] SoloMuScriptor, byte[] SoloBasicPitch, byte[] Bass, byte[] Orchestra, byte[] Drums);

/// <summary>WAV file bytes of the separated stems; each may be null.</summary>
public sealed record LayerStems(byte[]? Solo = null, byte[]? Bass = null, byte[]? Drums = null, byte[]? Orchestra = null);

/// <summary>Options of the solo-with-band arrangement.</summary>
/// <param name="Lineup">"band" (18 parts), "minimal" (8 parts) or "quartet" (1st Cornet, 2nd Cornet, Tenor Horn, Euphonium).</param>
/// <param name="Difficulty">"faithful", "standard" or "easier".</param>
/// <param name="Key">Target concert key of the first key signature (Bb, F#, Am or FIFTHS[:MODE]).</param>
/// <param name="Transpose">Semitones to transpose the whole arrangement by (instead of Key).</param>
public sealed record LayersSongOptions(SoloContour? SoloContour = null, bool FreeTime = true, double? FreeTempo = null,
    bool Gate = true, bool BeatCleanup = true, bool KeyChanges = true, string Lineup = "band", string Difficulty = "faithful",
    string? Key = null, int? Transpose = null);

/// <summary>Everything the band arrangement writes.</summary>
public sealed record BandOutput(string CompositionJson, string MusicXml, IReadOnlyList<(string FileName, string MusicXml)> Parts,
    string? SeparationCheckJson);

/// <summary>One part note for humanization: Composition ticks (24 per beat), score-tempo seconds, concert MIDI pitch.</summary>
public readonly record struct ScoreNote(long Tick, long DurTick, double StartS, double EndS, int Pitch, int Velocity);

/// <summary>A humanized note.</summary>
public readonly record struct PlayedNote(double Start, double End, int Pitch, int Velocity, bool Staccato, bool FromComposition);

/// <summary>Humanized notes of one player, the player's detune in cents, and the statistics as JSON.</summary>
public sealed record HumanizedPart(IReadOnlyList<PlayedNote> Notes, double DetuneCents, string StatsJson);

/// <summary>Talking-score announcer settings (docs/accessibility/talking-score-spec.md §2).</summary>
public sealed record TalkingSettings(string Lang = "en", string PitchMode = "written", string Verbosity = "standard",
    string OctaveStyle = "scientific", bool AnnounceConfident = false);

/// <summary>What the previous announcement left behind.</summary>
public sealed record TalkingContext(string? Part = null, long? Bar = null, string? PitchMode = null);

/// <summary>Indices of part, bar and event in a talking score.</summary>
public readonly record struct TalkingCursor(int Part, int Bar, int Event);

/// <summary>A talking score (spec §6), built once per score. Dispose to release the native document.</summary>
public sealed class TalkingScore : IDisposable
{
    private IntPtr _handle;

    /// <summary>From partwise MusicXML plus the Composition JSON when known.</summary>
    public TalkingScore(string musicXml, string? compositionJson = null)
    {
        int code = BrasscribeCore.NativeTalkingNew(musicXml, compositionJson, out _handle, out var err);
        if (code != 0) throw BrasscribeCore.Error(code, err);
    }

    /// <summary>The document as JSON.</summary>
    public string Json => BrasscribeCore.CallTalking(this, (IntPtr h, out IntPtr o, out IntPtr e) => BrasscribeCore.NativeTalkingJson(h, out o, out e));

    /// <summary>The announcement at a cursor and the context it leaves behind.</summary>
    public (string Text, TalkingContext Context) Announce(TalkingCursor cursor, TalkingContext? context = null, TalkingSettings? settings = null, bool byBar = false)
    {
        var request = JsonSerializer.Serialize(new
        {
            cursor = new { part = cursor.Part, bar = cursor.Bar, @event = cursor.Event },
            context = BrasscribeCore.ContextJson(context ?? new TalkingContext()),
            settings = BrasscribeCore.SettingsJson(settings ?? new TalkingSettings()),
            by_bar = byBar,
        });
        var json = BrasscribeCore.CallTalking(this, (IntPtr h, out IntPtr o, out IntPtr e) => BrasscribeCore.NativeTalkingAnnounce(h, request, out o, out e));
        using var doc = JsonDocument.Parse(json);
        var c = doc.RootElement.GetProperty("context");
        return (doc.RootElement.GetProperty("text").GetString()!,
            new TalkingContext(c.GetProperty("part").GetString(), c.GetProperty("bar").GetInt64(), c.GetProperty("pitch_mode").GetString()));
    }

    /// <summary>One step: unit "note", "bar", "part" or "uncertain". Null at either end.</summary>
    public TalkingCursor? Navigate(TalkingCursor cursor, string unit = "note", bool forward = true)
    {
        var request = JsonSerializer.Serialize(new { cursor = new { part = cursor.Part, bar = cursor.Bar, @event = cursor.Event }, unit, forward });
        var json = BrasscribeCore.CallTalking(this, (IntPtr h, out IntPtr o, out IntPtr e) => BrasscribeCore.NativeTalkingNavigate(h, request, out o, out e));
        using var doc = JsonDocument.Parse(json);
        var r = doc.RootElement;
        if (r.ValueKind == JsonValueKind.Null) return null;
        return new TalkingCursor(r.GetProperty("part").GetInt32(), r.GetProperty("bar").GetInt32(), r.GetProperty("event").GetInt32());
    }

    /// <summary>Export: format "text" or "html".</summary>
    public string Export(string format = "text", TalkingSettings? settings = null)
    {
        var s = JsonSerializer.Serialize(BrasscribeCore.SettingsJson(settings ?? new TalkingSettings()));
        return BrasscribeCore.CallTalking(this, (IntPtr h, out IntPtr o, out IntPtr e) => BrasscribeCore.NativeTalkingExport(h, format, s, out o, out e));
    }

    internal IntPtr Handle => _handle == IntPtr.Zero ? throw new ObjectDisposedException(nameof(TalkingScore)) : _handle;

    public void Dispose()
    {
        if (_handle != IntPtr.Zero)
        {
            BrasscribeCore.NativeTalkingFree(_handle);
            _handle = IntPtr.Zero;
        }
        GC.SuppressFinalize(this);
    }

    ~TalkingScore() => Dispose();
}

/// <summary>Managed API over the brasscribe_ffi C ABI.</summary>
public static class BrasscribeCore
{
    /// <summary>Version of the native core.</summary>
    public static string Version => TakeString(Native.bc_version()) ?? "";

    /// <summary>Parse a Composition JSON and return its canonical composition.json text.</summary>
    public static string NormalizeComposition(string compositionJson) =>
        Call((out IntPtr o, out IntPtr e) => Native.bc_composition_normalize(compositionJson, out o, out e));

    /// <summary>Arrange a Composition for brass band; returns MusicXML at written pitch.</summary>
    /// <param name="arranger">"auto", "layers" (solo with band) or "minimal".</param>
    public static string ArrangeMusicXml(string compositionJson, string arranger = "auto") =>
        Call((out IntPtr o, out IntPtr e) => Native.bc_arrange_musicxml(compositionJson, arranger, out o, out e));

    /// <summary>Re-arrange a Composition for a lineup and difficulty (optionally transposed); returns MusicXML at written pitch.</summary>
    /// <param name="lineup">"band" (18 parts), "minimal" (8 parts) or "quartet". A composition without layers (a whole-band
    /// take) is arranged for the minimal band or the quartet; "band" gives the minimal band there.</param>
    /// <param name="difficulty">"faithful", "standard" or "easier".</param>
    /// <param name="key">Target concert key of the first key signature (Bb, F#, Am or FIFTHS[:MODE]), or null.</param>
    /// <param name="transpose">Transposition from the recording in semitones (instead of key), or null: the total the
    /// composition records as arrangement.transpose_semitones, so an already transposed take is not moved again.</param>
    public static string ArrangeMusicXmlWith(string compositionJson, string lineup = "band", string difficulty = "faithful",
        string? key = null, int? transpose = null)
    {
        var options = JsonSerializer.Serialize(new { lineup, difficulty, key, transpose });
        return Call((out IntPtr o, out IntPtr e) => Native.bc_arrange_with(compositionJson, options, out o, out e));
    }

    /// <summary>Solo-with-band arrangement from layer transcriptions and a beat table ("time position" per line).</summary>
    /// <param name="soloContour">SwiftF0 contour of the solo stem (frame times, pitch in Hz, loudness in dB), or null.</param>
    /// <param name="freeTime">Detect free-time passages and notate them proportionally.</param>
    /// <param name="freeTempo">Notate free-time passages at this BPM instead of estimating one.</param>
    public static (string CompositionJson, string MusicXml) ArrangeLayersSong(LayerMidi layers, string beatsText, string title,
        SoloContour? soloContour = null, bool freeTime = true, double? freeTempo = null)
    {
        var options = JsonSerializer.Serialize(new
        {
            solo_contour = soloContour is null ? null : new { times = soloContour.Times, pitch_hz = soloContour.PitchHz, loudness_db = soloContour.LoudnessDb, confidence = soloContour.Confidence },
            free_time = freeTime,
            free_tempo = freeTempo,
        });
        byte[][] files = [layers.SoloSwiftF0, layers.SoloMuScriptor, layers.SoloBasicPitch, layers.Bass, layers.Orchestra, layers.Drums];
        var handles = files.Select(f => GCHandle.Alloc(f, GCHandleType.Pinned)).ToArray();
        try
        {
            var ptrs = handles.Select(h => h.AddrOfPinnedObject()).ToArray();
            var lens = files.Select(f => (nuint)f.Length).ToArray();
            int code = Native.bc_arrange_layers_song(ptrs, lens, beatsText, title, options, out var comp, out var xml, out var err);
            if (code != 0)
            {
                throw new BrasscribeException(code, TakeString(err) ?? $"brasscribe core error {code}");
            }
            return (TakeString(comp)!, TakeString(xml)!);
        }
        finally
        {
            foreach (var h in handles) h.Free();
        }
    }

    /// <summary>Solo-with-band arrangement with the stems' audio: the score, every part, the Composition and the separation check.</summary>
    public static BandOutput ArrangeLayersBand(LayerMidi layers, LayerStems? stems, string beatsText, string title, LayersSongOptions? options = null)
    {
        var o = options ?? new LayersSongOptions();
        var optionsJson = JsonSerializer.Serialize(new
        {
            solo_contour = o.SoloContour is null ? null : new { times = o.SoloContour.Times, pitch_hz = o.SoloContour.PitchHz, loudness_db = o.SoloContour.LoudnessDb, confidence = o.SoloContour.Confidence },
            free_time = o.FreeTime,
            free_tempo = o.FreeTempo,
            gate = o.Gate,
            beat_cleanup = o.BeatCleanup,
            key_changes = o.KeyChanges,
            lineup = o.Lineup,
            difficulty = o.Difficulty,
            key = o.Key,
            transpose = o.Transpose,
        });
        byte[][] files = [layers.SoloSwiftF0, layers.SoloMuScriptor, layers.SoloBasicPitch, layers.Bass, layers.Orchestra, layers.Drums];
        byte[]?[] wavs = [stems?.Solo, stems?.Bass, stems?.Drums, stems?.Orchestra];
        var handles = files.Select(f => GCHandle.Alloc(f, GCHandleType.Pinned)).ToList();
        var wavHandles = wavs.Select(w => w is null ? (GCHandle?)null : GCHandle.Alloc(w, GCHandleType.Pinned)).ToList();
        try
        {
            var ptrs = handles.Select(h => h.AddrOfPinnedObject()).ToArray();
            var lens = files.Select(f => (nuint)f.Length).ToArray();
            var wptrs = wavHandles.Select(h => h?.AddrOfPinnedObject() ?? IntPtr.Zero).ToArray();
            var wlens = wavs.Select(w => (nuint)(w?.Length ?? 0)).ToArray();
            var json = Call((out IntPtr r, out IntPtr e) => Native.bc_arrange_layers_band(ptrs, lens, wptrs, wlens, beatsText, title, optionsJson, out r, out e));
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var parts = root.GetProperty("parts").EnumerateArray()
                .Select(p => (p.GetProperty("file_name").GetString()!, p.GetProperty("musicxml").GetString()!)).ToList();
            var sep = root.GetProperty("separation_check");
            return new BandOutput(root.GetProperty("composition").GetString()!, root.GetProperty("musicxml").GetString()!, parts,
                sep.ValueKind == JsonValueKind.Null ? null : sep.GetString());
        }
        finally
        {
            foreach (var h in handles) h.Free();
            foreach (var h in wavHandles) h?.Free();
        }
    }

    /// <summary>Humanize one player's notes (sounds/README.md). performedTiming follows the recording (needs the Composition).</summary>
    public static HumanizedPart Humanize(IReadOnlyList<ScoreNote> notes, string part, int player, string seed = "brasscribe",
        string? compositionJson = null, bool performedTiming = false)
    {
        JsonElement? comp = compositionJson is null ? null : JsonDocument.Parse(compositionJson).RootElement;
        var request = JsonSerializer.Serialize(new
        {
            notes = notes.Select(n => new { tick = n.Tick, dur_tick = n.DurTick, start_s = n.StartS, end_s = n.EndS, pitch = n.Pitch, velocity = n.Velocity }),
            part,
            player,
            seed,
            timing = performedTiming ? "performed" : "score",
            composition = comp,
        });
        var json = Call((out IntPtr o, out IntPtr e) => Native.bc_humanize_json(request, out o, out e));
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        var played = root.GetProperty("notes").EnumerateArray().Select(x => new PlayedNote(x.GetProperty("start").GetDouble(),
            x.GetProperty("end").GetDouble(), x.GetProperty("pitch").GetInt32(), x.GetProperty("velocity").GetInt32(),
            x.GetProperty("staccato").GetBoolean(), x.GetProperty("from_composition").GetBoolean())).ToList();
        return new HumanizedPart(played, root.GetProperty("detune").GetDouble(), root.GetProperty("stats").GetRawText());
    }

    /// <summary>Announce one event given as JSON (the conformance-vector form: part, bar, event, context, settings).</summary>
    public static string TalkingAnnounceJson(string request) =>
        Call((out IntPtr o, out IntPtr e) => Native.bc_talking_announce_json(request, out o, out e));

    internal static object SettingsJson(TalkingSettings s) => new
    {
        lang = s.Lang, pitch_mode = s.PitchMode, verbosity = s.Verbosity, octave_style = s.OctaveStyle, announce_confident = s.AnnounceConfident,
    };

    internal static object ContextJson(TalkingContext c) => new { part = c.Part, bar = c.Bar, pitch_mode = c.PitchMode };

    internal static BrasscribeException Error(int code, IntPtr err) => new(code, TakeString(err) ?? $"brasscribe core error {code}");

    internal delegate int TalkingCall(IntPtr handle, out IntPtr output, out IntPtr error);

    internal static string CallTalking(TalkingScore ts, TalkingCall call)
    {
        int code = call(ts.Handle, out var output, out var error);
        GC.KeepAlive(ts);
        if (code != 0) throw Error(code, error);
        return TakeString(output) ?? "";
    }

    internal static int NativeTalkingNew(string xml, string? comp, out IntPtr handle, out IntPtr err) => Native.bc_talking_score_new(xml, comp, out handle, out err);
    internal static void NativeTalkingFree(IntPtr h) => Native.bc_talking_score_free(h);
    internal static int NativeTalkingJson(IntPtr h, out IntPtr o, out IntPtr e) => Native.bc_talking_score_json(h, out o, out e);
    internal static int NativeTalkingAnnounce(IntPtr h, string req, out IntPtr o, out IntPtr e) => Native.bc_talking_score_announce(h, req, out o, out e);
    internal static int NativeTalkingNavigate(IntPtr h, string req, out IntPtr o, out IntPtr e) => Native.bc_talking_score_navigate(h, req, out o, out e);
    internal static int NativeTalkingExport(IntPtr h, string format, string settings, out IntPtr o, out IntPtr e) => Native.bc_talking_score_export(h, format, settings, out o, out e);

    /// <summary>Spell MIDI pitches from their context (ps13); onsets in beats.</summary>
    public static IReadOnlyList<SpelledPitch> SpellPitches(IReadOnlyList<double> onsetsBeats, IReadOnlyList<int> pitches)
    {
        var request = JsonSerializer.Serialize(new { onsets = onsetsBeats, pitches });
        var json = Call((out IntPtr o, out IntPtr e) => Native.bc_spell_json(request, out o, out e));
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.EnumerateArray()
            .Select(x => new SpelledPitch(x.GetProperty("step").GetString()!, x.GetProperty("alter").GetInt32(), x.GetProperty("octave").GetInt32()))
            .ToList();
    }

    private delegate int NativeCall(out IntPtr output, out IntPtr error);

    private static string Call(NativeCall call)
    {
        int code = call(out var output, out var error);
        if (code != 0)
        {
            throw new BrasscribeException(code, TakeString(error) ?? $"brasscribe core error {code}");
        }
        return TakeString(output) ?? "";
    }

    /// <summary>Copy a UTF-8 string owned by the native library and release it.</summary>
    private static string? TakeString(IntPtr p)
    {
        if (p == IntPtr.Zero) return null;
        try
        {
            return Marshal.PtrToStringUTF8(p);
        }
        finally
        {
            Native.bc_string_free(p);
        }
    }

    private static class Native
    {
        private const string Lib = "brasscribe_ffi";

        [DllImport(Lib)] public static extern void bc_string_free(IntPtr s);
        [DllImport(Lib)] public static extern IntPtr bc_version();

        [DllImport(Lib)]
        public static extern int bc_composition_normalize([MarshalAs(UnmanagedType.LPUTF8Str)] string json, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_arrange_musicxml([MarshalAs(UnmanagedType.LPUTF8Str)] string json,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string arranger, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_arrange_with([MarshalAs(UnmanagedType.LPUTF8Str)] string json,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string? optionsJson, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_arrange_layers_song(IntPtr[] midi, nuint[] midiLen,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string beatsText, [MarshalAs(UnmanagedType.LPUTF8Str)] string title,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string? optionsJson,
            out IntPtr outComposition, out IntPtr outMusicXml, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_spell_json([MarshalAs(UnmanagedType.LPUTF8Str)] string request, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_arrange_layers_band(IntPtr[] midi, nuint[] midiLen, IntPtr[] wav, nuint[] wavLen,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string beatsText, [MarshalAs(UnmanagedType.LPUTF8Str)] string title,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string? optionsJson, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_humanize_json([MarshalAs(UnmanagedType.LPUTF8Str)] string request, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_talking_score_new([MarshalAs(UnmanagedType.LPUTF8Str)] string musicXml,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string? compositionJson, out IntPtr handle, out IntPtr error);

        [DllImport(Lib)] public static extern void bc_talking_score_free(IntPtr handle);

        [DllImport(Lib)] public static extern int bc_talking_score_json(IntPtr handle, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_talking_score_announce(IntPtr handle, [MarshalAs(UnmanagedType.LPUTF8Str)] string request, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_talking_score_navigate(IntPtr handle, [MarshalAs(UnmanagedType.LPUTF8Str)] string request, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_talking_score_export(IntPtr handle, [MarshalAs(UnmanagedType.LPUTF8Str)] string format,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string? settingsJson, out IntPtr output, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_talking_announce_json([MarshalAs(UnmanagedType.LPUTF8Str)] string request, out IntPtr output, out IntPtr error);
    }
}
