using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

public sealed class BrassSoundSetTests(ITestOutputHelper log)
{
    /// <summary>A minimal SoundFont2: an INFO list, then a pdta list with an odd-sized chunk before phdr (two presets and EOP).</summary>
    internal static byte[] TinySf2(params ushort[] programs)
    {
        static byte[] Chunk(string id, byte[] body)
        {
            var c = new byte[8 + body.Length + (body.Length & 1)];
            Encoding.ASCII.GetBytes(id).CopyTo(c, 0);
            BinaryPrimitives.WriteInt32LittleEndian(c.AsSpan(4), body.Length);
            body.CopyTo(c, 8);
            return c;
        }
        static byte[] List(string type, params byte[][] chunks) => Chunk("LIST", [.. Encoding.ASCII.GetBytes(type), .. chunks.SelectMany(c => c)]);
        var phdr = new byte[(programs.Length + 1) * 38];
        for (int i = 0; i <= programs.Length; i++)
        {
            var rec = phdr.AsSpan(i * 38, 38);
            Encoding.ASCII.GetBytes(i < programs.Length ? $"Preset {i}" : "EOP").CopyTo(rec);
            BinaryPrimitives.WriteUInt16LittleEndian(rec[20..], i < programs.Length ? programs[i] : (ushort)0);
            BinaryPrimitives.WriteUInt16LittleEndian(rec[22..], (ushort)(i == 1 ? 128 : 0)); // bank
            BinaryPrimitives.WriteUInt16LittleEndian(rec[24..], (ushort)i); // bag index
        }
        var body = new byte[][]
        {
            [.. "sfbk"u8],
            List("INFO", Chunk("ifil", [2, 0, 1, 0])),
            List("pdta", Chunk("xtra", [1, 2, 3]), Chunk("phdr", phdr)),
        }.SelectMany(b => b).ToArray();
        return Chunk("RIFF", body);
    }

    private static string Sha(byte[] b) => Convert.ToHexStringLower(SHA256.HashData(b));

    /// <summary>Without mapping.json, a trumpet player's lead part ("Trumpet") plays the Solo Cornet's sound.</summary>
    [Fact]
    public void The_trumpet_part_plays_the_solo_cornets_sound_without_a_mapping()
    {
        string Folder(string part) => BrassSoundSet.PartMap.First(m => part.Contains(m.PartContains, StringComparison.OrdinalIgnoreCase)).Instrument;
        Assert.Equal("cornet-b", Folder("Trumpet"));
        Assert.Equal(Folder("Solo Cornet"), Folder("Trumpet"));
    }

    /// <summary>SHA-256 of MovePresets' output from before it patched in place (it cloned then), per offset.</summary>
    [SkippableTheory]
    [InlineData(0, "032f22e0f58c379876dd1cac6920392e050b0957ddfbaed269ef406dfc271832", "4978cf37e7164206f2d22dc4fdf4020ffe040787210bf781e31bdc79961f59ef")]
    [InlineData(2, "59fc93ee9249ed73ccee201b691d30ef56355221edb2e8bc4a5ed0e57b81bbec", "51422ef01524a236c561b448a672d6c4f07043ea71e3abe09d7a769b3ba489f3")]
    [InlineData(20, "67f1609fc139aab594c8a75c595b46626995624f720896b4a0771a1df0e95aeb", "5472e8edcbb7e809610df629cdc285d48319e43de2ca7620b3e71b287e33732b")]
    [InlineData(126, "c9e72d9798ae44efa27fa8a0c19b2bc07242ab465b5166e24dc541d5c6a91648", "2da43708e81f057630ac8cf281a0c5882b528caa81fd152adb79b88f8f0fa13d")]
    public void Moving_presets_in_place_gives_the_same_bytes_as_before_without_a_copy(int offset, string tiny, string sonivox)
    {
        var sf2 = TinySf2(0, 1);
        var moved = BrassSoundSet.MovePresets(sf2, offset);
        Assert.Same(sf2, moved);
        Assert.Equal(tiny, Sha(moved));
        // The second preset (program 1) is the record before EOP, at the end of the file.
        Assert.Equal((ushort)Math.Min(127, 1 + offset), BinaryPrimitives.ReadUInt16LittleEndian(moved.AsSpan(moved.Length - 2 * 38 + 20)));

        var path = TestPaths.RepoFile(Sonivox);
        Skip.If(path is null, TestPaths.Missing(Sonivox));
        Assert.Equal(sonivox, Sha(BrassSoundSet.MovePresets(File.ReadAllBytes(path), offset)));
    }

    private const string Sonivox = "engine/src/brasscribe_engine/static/assets/alphatab/soundfont/sonivox.sf2";

    /// <summary>
    /// The app lists the set before its first frame; the files (about 283 MB in a dev build) must not be
    /// read then, only by ApplyTo, one at a time.
    /// </summary>
    [SkippableFact]
    public async Task Load_only_lists_the_files_and_ApplyTo_reads_them_in_the_background()
    {
        var small = TestPaths.RepoFile(Sonivox);
        Skip.If(small is null, TestPaths.Missing(Sonivox));
        var dir = Directory.CreateTempSubdirectory("brass-set").FullName;
        try
        {
            foreach (var n in new[] { "cornet-a", "tenor-horn" })
            {
                Directory.CreateDirectory(Path.Combine(dir, n));
                File.Copy(small, Path.Combine(dir, n, n + ".sf2"));
            }
            BrassSoundSet set;
            // Locked: reading a file inside Load would throw.
            using (new FileStream(Path.Combine(dir, "cornet-a", "cornet-a.sf2"), FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            using (new FileStream(Path.Combine(dir, "tenor-horn", "tenor-horn.sf2"), FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                Assert.Throws<IOException>(() => File.ReadAllBytes(Path.Combine(dir, "cornet-a", "cornet-a.sf2")));
                set = BrassSoundSet.Load(dir);
            }
            Assert.Equal(2, set.Files.Count);
            Assert.Equal(0, set.Programs["cornet-a"]);
            Assert.Equal(2, set.Programs["tenor-horn"]);

            using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
            var loading = set.ApplyTo(player, inBackground: true);
            Assert.NotNull(player.ProgramMap); // parts are routed before any file is read
            Assert.Equal(2, player.ProgramMap!("Tenor Horn"));
            await loading;
            Assert.True(player.HasSoundFont);
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    /// <summary>
    /// Opt-in measurement with a real dev set (BRASSCRIBE_BUILT_SOUNDS=&lt;checkout&gt;/data/sounds/built):
    /// managed bytes allocated and still held after Load, and the managed heap after ApplyTo.
    /// </summary>
    [SkippableFact]
    public void Measure_the_dev_set()
    {
        var dir = Environment.GetEnvironmentVariable("BRASSCRIBE_BUILT_SOUNDS");
        Skip.If(dir is null || !Directory.Exists(dir), "opt-in measurement: set BRASSCRIBE_BUILT_SOUNDS to a built sound set (<checkout>/data/sounds/built)");
        long before = GC.GetTotalMemory(true), allocated = GC.GetTotalAllocatedBytes(true);
        var set = BrassSoundSet.Load(dir);
        long loadAlloc = GC.GetTotalAllocatedBytes(true) - allocated;
        long loadHeld = GC.GetTotalMemory(true) - before;
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        set.ApplyTo(player);
        long applyAlloc = GC.GetTotalAllocatedBytes(true) - allocated - loadAlloc;
        log.WriteLine($"MEASURE Load: allocated {loadAlloc / 1e6:F1} MB, held {loadHeld / 1e6:F1} MB; " +
                      $"ApplyTo: allocated {applyAlloc / 1e6:F0} MB, heap after {(GC.GetTotalMemory(true) - before) / 1e6:F0} MB");
        GC.KeepAlive(set);
    }
}
