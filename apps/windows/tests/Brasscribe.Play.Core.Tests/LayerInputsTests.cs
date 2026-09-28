using System.Buffers.Binary;
using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using Brasscribe.Play.Core.Arrangement;

namespace Brasscribe.Play.Core.Tests;

public sealed class LayerInputsTests : IDisposable
{
    private readonly string _root = Directory.CreateTempSubdirectory("layers").FullName;
    public void Dispose() => Directory.Delete(_root, recursive: true);

    private string CachedJob(string jobId)
    {
        var dir = Path.Combine(_root, jobId);
        Directory.CreateDirectory(dir);
        foreach (var name in LayerInputs.MidiNames) File.WriteAllBytes(Path.Combine(dir, name), Encoding.ASCII.GetBytes("MThd " + name));
        File.WriteAllText(Path.Combine(dir, LayerInputs.BeatsName), "0.5\n1.0\n");
        File.WriteAllText(Path.Combine(dir, ".complete"), "");
        return dir;
    }

    /// <summary>
    /// A cache hit reads every stem from disk; OutputOptionsViewModel awaits it on the UI thread, so the
    /// reading must happen after LoadAsync has returned. The solo stem is a FIFO here: reading it waits
    /// until the test writes, so a LoadAsync that reads before returning never returns.
    /// </summary>
    [Fact]
    public async Task A_cache_hit_reads_the_stems_after_returning_to_the_caller()
    {
        if (OperatingSystem.IsWindows()) return; // no mkfifo
        var dir = CachedJob("job-1");
        var solo = Path.Combine(dir, "solo.wav");
        using (var mk = Process.Start(new ProcessStartInfo("mkfifo", [solo]) { UseShellExecute = false })!)
        {
            mk.WaitForExit();
            Assert.Equal(0, mk.ExitCode);
        }
        var stem = new byte[300_000];
        new Random(7).NextBytes(stem);

        Task<LayerInputs?>? loading = null;
        // A thread of its own: if LoadAsync blocked on the FIFO, the test fails instead of hanging.
        var caller = new Thread(() => loading = EngineLayerSource.LoadAsync(null!, "job-1", _root)) { IsBackground = true };
        caller.Start();
        bool returned = caller.Join(TimeSpan.FromSeconds(3));
        try
        {
            Assert.True(returned, "LoadAsync read the stems before returning");
            Assert.False(loading!.IsCompleted);
        }
        finally
        {
            // Let the read finish either way (opening a FIFO for writing waits for its reader).
            var write = Task.Run(() => { using var w = new FileStream(solo, FileMode.Open, FileAccess.Write); w.Write(stem); });
            await write.WaitAsync(TimeSpan.FromSeconds(10));
        }
        var inputs = await loading!.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.NotNull(inputs);
        Assert.Equal(stem, inputs.Wav[0]);
        Assert.Null(inputs.Wav[1]);
        Assert.Equal("0.5\n1.0\n", inputs.Beats);
    }

    /// <summary>np.savez layout: one .npy per array (v1 header), little-endian.</summary>
    private static byte[] Npz(bool float32, params (string Name, double[] Values)[] arrays)
    {
        var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
            foreach (var (name, values) in arrays)
            {
                string header = $"{{'descr': '{(float32 ? "<f4" : "<f8")}', 'fortran_order': False, 'shape': ({values.Length},), }}";
                header = header.PadRight(64 - 10 - 1) + "\n";
                using var s = zip.CreateEntry(name + ".npy", CompressionLevel.Optimal).Open();
                s.Write([0x93, .. "NUMPY"u8, 1, 0]);
                Span<byte> len = stackalloc byte[2];
                BinaryPrimitives.WriteUInt16LittleEndian(len, (ushort)header.Length);
                s.Write(len);
                s.Write(Encoding.ASCII.GetBytes(header));
                Span<byte> v = stackalloc byte[8];
                foreach (var x in values)
                {
                    if (float32) BinaryPrimitives.WriteSingleLittleEndian(v, (float)x);
                    else BinaryPrimitives.WriteDoubleLittleEndian(v, x);
                    s.Write(v[..(float32 ? 4 : 8)]);
                }
            }
        return ms.ToArray();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void The_contour_read_from_the_file_equals_the_contour_read_from_its_bytes(bool float32)
    {
        var dir = CachedJob("job-2");
        double[] t = [0, 0.01, 0.02, 0.03], hz = [440, 441.5, double.NaN, 0], db = [-20, -21.25, -140, -60];
        var npz = Npz(float32, ("t", t), ("pitch_hz", hz), ("loudness_db", db));
        File.WriteAllBytes(Path.Combine(dir, LayerInputs.ContourName), npz);

        var fromFile = LayerInputs.FromDirectory(dir)!.Contour!;
        var fromBytes = LayerInputs.ReadContour(npz);
        Assert.Equal(fromBytes.Times, fromFile.Times);
        Assert.Equal(fromBytes.PitchHz, fromFile.PitchHz);
        Assert.Equal(fromBytes.LoudnessDb, fromFile.LoudnessDb);
        Assert.Equal(float32 ? t.Select(x => (double)(float)x) : t, fromFile.Times);
        Assert.True(double.IsNaN(fromFile.PitchHz[2]));
    }
}
