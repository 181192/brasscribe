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

/// <summary>The six layer transcriptions (MIDI file bytes) of a recording.</summary>
public sealed record LayerMidi(byte[] SoloSwiftF0, byte[] SoloMuScriptor, byte[] SoloBasicPitch, byte[] Bass, byte[] Orchestra, byte[] Drums);

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

    /// <summary>Solo-with-band arrangement from layer transcriptions and a beat table ("time position" per line).</summary>
    public static (string CompositionJson, string MusicXml) ArrangeLayersSong(LayerMidi layers, string beatsText, string title)
    {
        byte[][] files = [layers.SoloSwiftF0, layers.SoloMuScriptor, layers.SoloBasicPitch, layers.Bass, layers.Orchestra, layers.Drums];
        var handles = files.Select(f => GCHandle.Alloc(f, GCHandleType.Pinned)).ToArray();
        try
        {
            var ptrs = handles.Select(h => h.AddrOfPinnedObject()).ToArray();
            var lens = files.Select(f => (nuint)f.Length).ToArray();
            int code = Native.bc_arrange_layers_song(ptrs, lens, beatsText, title, out var comp, out var xml, out var err);
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
        public static extern int bc_arrange_layers_song(IntPtr[] midi, nuint[] midiLen,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string beatsText, [MarshalAs(UnmanagedType.LPUTF8Str)] string title,
            out IntPtr outComposition, out IntPtr outMusicXml, out IntPtr error);

        [DllImport(Lib)]
        public static extern int bc_spell_json([MarshalAs(UnmanagedType.LPUTF8Str)] string request, out IntPtr output, out IntPtr error);
    }
}
