using System.Runtime.InteropServices;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// The realistic playback tier: sfizz (BSD-2) rendering the SFZ instruments under sounds/
/// (VSCO 2 CE and Iowa MIS brass mapped to brass-band parts). This is a seam: the P/Invoke
/// declarations follow sfizz's C API (sfizz.h), but sfizz.dll is not built or shipped yet, so
/// <see cref="TryCreate"/> returns null and playback stays on the alphaTab SoundFont tier.
/// Open work: build sfizz for win-x64/arm64, drive it from alphaTab's MIDI events per part
/// (IAlphaSynth.MidiEventsPlayed), and mix the per-part renders with room IRs.
/// </summary>
public sealed partial class SfizzEngine : IDisposable
{
    private const string Lib = "sfizz";
    private nint _synth;

    private SfizzEngine(nint synth) => _synth = synth;

    public static bool IsAvailable => NativeLibrary.TryLoad(Lib, typeof(SfizzEngine).Assembly, null, out _);

    public static SfizzEngine? TryCreate(int sampleRate, int blockSize)
    {
        if (!IsAvailable) return null;
        try
        {
            nint s = sfizz_create_synth();
            if (s == 0) return null;
            sfizz_set_sample_rate(s, sampleRate);
            sfizz_set_samples_per_block(s, blockSize);
            return new SfizzEngine(s);
        }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException)
        {
            return null;
        }
    }

    public bool LoadSfz(string path) => sfizz_load_file(_synth, path);

    public void NoteOn(int delay, int note, int velocity) => sfizz_send_note_on(_synth, delay, note, velocity);
    public void NoteOff(int delay, int note, int velocity) => sfizz_send_note_off(_synth, delay, note, velocity);

    /// <summary>Renders one block into planar left/right buffers.</summary>
    public unsafe void Render(Span<float> left, Span<float> right)
    {
        fixed (float* l = left)
        fixed (float* r = right)
        {
            var channels = stackalloc float*[2];
            channels[0] = l;
            channels[1] = r;
            sfizz_render_block(_synth, channels, 2, left.Length);
        }
    }

    public void Dispose()
    {
        if (_synth != 0) sfizz_free(_synth);
        _synth = 0;
    }

    [LibraryImport(Lib)] private static partial nint sfizz_create_synth();
    [LibraryImport(Lib)] private static partial void sfizz_free(nint synth);
    [LibraryImport(Lib)] private static partial void sfizz_set_sample_rate(nint synth, float rate);
    [LibraryImport(Lib)] private static partial void sfizz_set_samples_per_block(nint synth, int size);

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    [return: MarshalAs(UnmanagedType.U1)]
    private static partial bool sfizz_load_file(nint synth, string path);

    [LibraryImport(Lib)] private static partial void sfizz_send_note_on(nint synth, int delay, int note, int velocity);
    [LibraryImport(Lib)] private static partial void sfizz_send_note_off(nint synth, int delay, int note, int velocity);
    [LibraryImport(Lib)] private static unsafe partial void sfizz_render_block(nint synth, float** channels, int numChannels, int numFrames);
}
