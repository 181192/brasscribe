using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The band SoundFont as the app uses it: the part map from sounds/mapping.json, one MIDI channel
/// per part with drums on channel 10, balance from channel_gain_db, drum notes for unpitched
/// notes, and a MIDI export that fits 16 channels without a brass part on the drum channel.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class BandPlaybackTests(ITestOutputHelper log)
{
    private static string? Mapping => TestPaths.RepoFile("sounds/mapping.json");

    private static IReadOnlyList<ChannelPlan.Part> Band() =>
    [
        .. Enumerable.Range(0, 17).Select(i => new ChannelPlan.Part(i, false, i < 6 ? 56 : i < 9 ? 60 : i < 11 ? 58 : i < 14 ? 57 : 58, i is 3 or 4 ? -11 : -4)),
        new ChannelPlan.Part(17, true, 0, -9.5),
    ];

    [Fact]
    public void Playback_gives_every_part_its_own_channel_and_drums_channel_10()
    {
        var ch = ChannelPlan.ForPlayback(Band());
        Assert.Equal(ChannelPlan.Drums, ch[17]);
        Assert.Equal(17, ch.Take(17).Distinct().Count());
        Assert.DoesNotContain(ChannelPlan.Drums, ch.Take(17));
        Assert.DoesNotContain(ChannelPlan.Metronome, ch);
    }

    [Fact]
    public void Midi_file_fits_16_channels_by_sharing_like_parts()
    {
        var parts = Band();
        var ch = ChannelPlan.ForMidiFile(parts);
        Assert.All(ch, c => Assert.InRange(c, 0, 15));
        Assert.Equal(ChannelPlan.Drums, ch[17]);
        Assert.DoesNotContain(ChannelPlan.Drums, ch.Take(17));
        Assert.Equal(15, ch.Take(17).Distinct().Count());
        // Parts that share a channel play the same program.
        foreach (var g in ch.Take(17).Select((c, i) => (c, i)).GroupBy(x => x.c))
            Assert.Single(g.Select(x => parts[x.i].Program).Distinct());
    }

    [Fact]
    public void Mapping_covers_the_arranger_part_names()
    {
        if (Mapping is null) return;
        var band = BandSoundFont.Load(Mapping);
        foreach (var name in new[] { "Soprano Cornet", "Solo Cornet", "Flugelhorn", "Solo Horn", "1st Baritone", "Bass Trombone", "Euphonium", "E♭ Bass", "B♭ Bass" })
            Assert.NotNull(band.For(name));
        Assert.Equal((56, 5), (band.For("Flugelhorn")!.Program, band.For("Flugelhorn")!.Bank));
        Assert.True(band.For("Percussion")!.Percussion);
    }

    [Fact]
    public void Golden_score_plays_every_part_including_drums_with_the_band_soundfont()
    {
        var sf2 = TestPaths.RepoFile("data/sounds/band/brasscribe-band.sf2");
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (Mapping is null || sf2 is null || golden is null) return;

        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        var band = BandSoundFont.Load(Mapping, sf2);
        band.ApplyTo(player);
        player.LoadScore(File.ReadAllBytes(golden));
        Assert.True(player.IsReady, player.LoadError?.Message);

        var channels = player.TrackChannels;
        var perc = player.Tracks.Single(t => t.IsPercussion).Index;
        Assert.Equal(ChannelPlan.Drums, channels[perc]);
        Assert.Equal(channels.Count, channels.Distinct().Count());
        Assert.Equal(Math.Pow(10, band.For("Percussion")!.GainDb / 20), player.TrackGains[perc], 6);

        var levels = new List<string>();
        var silent = new List<string>();
        foreach (var track in player.Tracks)
        {
            foreach (var t in player.Tracks) player.SetSolo(t.Index, t.Index == track.Index);
            player.SeekToBar(50);
            player.Play();
            var buffer = new float[2 * 1024];
            double sum = 0;
            long n = 0;
            for (int i = 0; i < 44100 * 4 / 1024; i++)
            {
                output.Read(buffer);
                foreach (var v in buffer) sum += v * v;
                n += buffer.Length;
            }
            player.Pause();
            double rms = Math.Sqrt(sum / n);
            levels.Add($"{track.Name} ch{channels[track.Index]} {rms:0.0000}");
            bool hasNotes = player.Score!.Tracks[track.Index].Staves.SelectMany(st => st.Bars).Skip(50).Take(2).SelectMany(b => b.Voices)
                .SelectMany(v => v.Beats).Any(b => b.Notes.Count > 0);
            if (hasNotes && rms < 1e-4) silent.Add(track.Name);
        }
        log.WriteLine("band SF2, bar 51, per track: " + string.Join("; ", levels));
        Assert.Empty(silent);

        // The exported file: no pitched part on the drum channel, at most 16 channels.
        var midi = player.ExportMidi();
        var (drumTracks, used) = NoteChannels(midi);
        log.WriteLine($"export: channels {string.Join(",", used.Order())}; tracks with notes on channel 10: {string.Join(",", drumTracks)}");
        Assert.All(used, c => Assert.InRange(c, 0, 15));
        Assert.Single(drumTracks);
    }

    /// <summary>Channels with note-on events in a Standard MIDI File, and the MTrk indexes that play on channel 10.</summary>
    private static (List<int> DrumTracks, HashSet<int> Channels) NoteChannels(byte[] smf)
    {
        var drumTracks = new List<int>();
        var channels = new HashSet<int>();
        int pos = 14, track = 0;
        while (pos + 8 <= smf.Length)
        {
            int len = (smf[pos + 4] << 24) | (smf[pos + 5] << 16) | (smf[pos + 6] << 8) | smf[pos + 7];
            if (smf[pos] == 'M' && smf[pos + 1] == 'T' && smf[pos + 2] == 'r' && smf[pos + 3] == 'k')
            {
                int p = pos + 8, end = p + len, running = 0;
                bool drums = false;
                while (p < end)
                {
                    while ((smf[p++] & 0x80) != 0) { } // delta time
                    int status = smf[p];
                    if (status >= 0x80) p++; else status = running;
                    if (status == 0xFF) { int type = smf[p++]; int l = 0; while (true) { int b = smf[p++]; l = (l << 7) | (b & 0x7F); if ((b & 0x80) == 0) break; } p += l; continue; }
                    if (status is 0xF0 or 0xF7) { int l = 0; while (true) { int b = smf[p++]; l = (l << 7) | (b & 0x7F); if ((b & 0x80) == 0) break; } p += l; continue; }
                    running = status;
                    int kind = status & 0xF0, ch = status & 0x0F;
                    int data = kind is 0xC0 or 0xD0 ? 1 : 2;
                    if (kind == 0x90 && smf[p + 1] > 0)
                    {
                        channels.Add(ch);
                        if (ch == 9) drums = true;
                    }
                    p += data;
                }
                if (drums) drumTracks.Add(track);
                track++;
            }
            pos += 8 + len;
        }
        return (drumTracks, channels);
    }
}
